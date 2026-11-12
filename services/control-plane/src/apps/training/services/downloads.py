"""Authorized file/folder downloads without persisting derived archives in S3."""
import hashlib
import mimetypes
import stat
from contextlib import closing
from tempfile import SpooledTemporaryFile
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

from rest_framework.exceptions import NotFound, ValidationError

from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage
from .storage_scope import training_prefix_for, validate_training_uri
from .workspaces import MAX_WORKSPACE_SNAPSHOT, safe_path

MAX_OUTPUT_DOWNLOAD = 20 * 1024**3 + 512 * 1024**2
MAX_ENTRIES = 20_000
CHUNK_SIZE = 1024 * 1024


class _DownloadBuffer(SpooledTemporaryFile):
    def seekable(self):
        # ZipFile needs this method; SpooledTemporaryFile gained it in Python 3.11.
        # Control Plane's container still uses Python 3.10.
        return not self.closed


def _temporary():
    return _DownloadBuffer(max_size=8 * 1024 * 1024, mode="w+b")


def _copy(source, destination, remaining, checksum=""):
    size = 0
    digest = hashlib.sha256()
    while chunk := source.read(CHUNK_SIZE):
        size += len(chunk)
        if size > remaining:
            raise ValidationError("Download exceeds the allowed size.")
        digest.update(chunk)
        destination.write(chunk)
    if checksum and digest.hexdigest() != checksum:
        raise Conflict("File integrity verification failed.")
    return size


def _selection(paths, path):
    if path is not None:
        safe_path(path)
    if path in paths:
        return [path], True
    selected = [name for name in paths if path is None or name.startswith(path + "/")]
    if not selected:
        raise NotFound("No files are available for this selection.")
    return selected, False


def _filename(path, area, single):
    return path.rsplit("/", 1)[-1] if single else f"{path.rsplit('/', 1)[-1] if path else area}.zip"


def _archive_name(name, path):
    # Keep the selected folder as the ZIP root, without unrelated parent folders.
    return name[len(path.rpartition('/')[0]) + 1:] if path and "/" in path else name


def _result(stream, filename):
    stream.seek(0)
    return stream, filename, mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _snapshot(job, storage, path):
    try:
        validate_training_uri(job, storage.bucket, "code", job.code_snapshot_uri)
    except ValueError as exc:
        raise Conflict("Input snapshot is outside its job storage scope.") from exc
    original = _temporary()
    result = None
    try:
        source, _, _ = storage.open_stream(job.code_snapshot_uri)
        with closing(source):
            _copy(source, original, MAX_WORKSPACE_SNAPSHOT)
        original.seek(0)
        with ZipFile(original) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES or sum(item.file_size for item in infos) > MAX_WORKSPACE_SNAPSHOT:
                raise ValidationError("Input snapshot exceeds the allowed size.")
            names = set()
            files = {}
            for item in infos:
                name = safe_path(item.filename.rstrip("/"))
                mode = stat.S_IFMT(item.external_attr >> 16)
                if name in names or mode not in {0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG} or item.flag_bits & 1:
                    raise ValidationError("Input snapshot contains invalid entries.")
                names.add(name)
                if not item.is_dir():
                    files[name] = item
            selected, single = _selection(files, path)
            if path is None:
                return _result(original, "input.zip")
            result = _temporary()
            if single:
                with archive.open(files[path]) as source:
                    _copy(source, result, MAX_WORKSPACE_SNAPSHOT)
            else:
                with ZipFile(result, "w", ZIP_DEFLATED) as bundle:
                    for name in selected:
                        with archive.open(files[name]) as source, bundle.open(_archive_name(name, path), "w") as target:
                            _copy(source, target, files[name].file_size)
                    for item in infos:
                        if item.is_dir() and (item.filename.rstrip("/") == path or item.filename.startswith(path + "/")):
                            bundle.writestr(_archive_name(item.filename, path), b"")
            return _result(result, _filename(path, "input", single))
    except Exception as exc:
        if result is not None:
            result.close()
        original.close()
        if isinstance(exc, BadZipFile):
            raise ValidationError("Input snapshot is not a valid ZIP archive.") from exc
        raise
    finally:
        if path is not None:
            original.close()


def workspace_download(job, *, area, path=None, revision=None, storage=None):
    """Caller authorizes the job first. This service accepts paths, never storage URIs."""
    storage = storage or S3Storage()
    if area == "input" and job.submitted_at:
        return _snapshot(job, storage, path)
    if area == "input":
        if revision is not None and str(job.revision) != str(revision):
            raise Conflict("Workspace changed. Reload before downloading.")
        entries = list(job.entries.all())
        files = {entry.relative_path: entry for entry in entries if entry.kind != "folder"}
        prefix = f"users/{job.owner.tenant_id}/training/jobs/{job.public_id}/draft/objects/"
        limit = MAX_WORKSPACE_SNAPSHOT
    elif area == "output":
        if job.outputs_purged_at:
            raise Conflict("Training outputs have been purged.")
        from .output_index import public_outputs
        entries = list(public_outputs(job))
        files = {entry.relative_path: entry for entry in entries}
        prefix = training_prefix_for(job) + "/"
        limit = MAX_OUTPUT_DOWNLOAD
    else:
        raise ValidationError("Invalid download area.")
    if len(entries) > MAX_ENTRIES:
        raise ValidationError("Too many files to download.")
    selected, single = _selection(files, path)
    stream = _temporary()
    try:
        remaining = limit

        def copy_file(name, target):
            nonlocal remaining
            safe_path(name)
            entry = files[name]
            bucket, key = storage.parse_uri(entry.s3_uri)
            if bucket != storage.bucket or not key.startswith(prefix):
                raise Conflict("File is outside its job storage scope.")
            source, size, _ = storage.open_stream(entry.s3_uri)
            with closing(source):
                if size is not None and size > remaining:
                    raise ValidationError("Download exceeds the allowed size.")
                remaining -= _copy(source, target, remaining, entry.checksum)

        if single:
            copy_file(path, stream)
        else:
            with ZipFile(stream, "w", ZIP_DEFLATED if area == "input" else ZIP_STORED, allowZip64=True) as archive:
                for name in selected:
                    with archive.open(_archive_name(name, path), "w", force_zip64=True) as target:
                        copy_file(name, target)
                if area == "input":
                    for entry in entries:
                        if entry.kind == "folder" and (path is None or entry.relative_path == path or entry.relative_path.startswith(path + "/")):
                            safe_path(entry.relative_path)
                            archive.writestr(_archive_name(entry.relative_path + "/", path), b"")
        if area == "input" and not type(job).objects.filter(pk=job.pk, revision=job.revision).exists():
            raise Conflict("Workspace changed. Reload before downloading.")
        return _result(stream, _filename(path, area, single))
    except Exception:
        stream.close()
        raise
