from zipfile import ZipFile

from rest_framework.exceptions import ValidationError

from apps.training.jobs.storage_scope import training_prefix_for, validate_training_uri
from apps.training.workspace.editing import safe_path
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage


def input_snapshot(job, *, path=None, download=False, storage=None):
    from tempfile import SpooledTemporaryFile

    storage = storage or S3Storage()
    try:
        validate_training_uri(job, storage.bucket, "code", job.code_snapshot_uri)
    except ValueError as exc:
        raise Conflict("Training input snapshot is not ready.") from exc
    if download:
        return {"download_url": storage.presigned_get(job.code_snapshot_uri, public=True)}
    max_archive_bytes = 256 * 1024 * 1024
    with SpooledTemporaryFile(max_size=8 * 1024 * 1024) as handle:
        if hasattr(storage, "open_stream"):
            body, _, _ = storage.open_stream(job.code_snapshot_uri)
            total = 0
            try:
                while chunk := body.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_archive_bytes:
                        raise ValidationError("Snapshot is too large to preview. Download the archive instead.")
                    handle.write(chunk)
            finally:
                body.close()
        else:
            handle.write(storage.read(job.code_snapshot_uri, max_bytes=max_archive_bytes))
        handle.seek(0)
        with ZipFile(handle) as archive:
            if len(archive.infolist()) > 20_000 or sum(info.file_size for info in archive.infolist()) > max_archive_bytes:
                raise ValidationError("Snapshot is too large to preview. Download the archive instead.")
            if path:
                safe_path(path)
                try:
                    info = archive.getinfo(path)
                except KeyError:
                    raise ValidationError("Snapshot file does not exist.") from None
                if info.file_size > 100 * 1024 * 1024 or info.is_dir():
                    raise ValidationError("Snapshot file cannot be previewed.")
                return {"content": archive.read(info).decode("utf-8", errors="replace")}
            entries = []
            kinds = {".py": "script", ".csv": "data", ".json": "config", ".md": "document"}
            for info in archive.infolist():
                relative = safe_path(info.filename.rstrip("/"))
                kind = (
                    "folder"
                    if info.is_dir()
                    else (
                        "requirements"
                        if relative == "requirements.txt"
                        else next((kind for suffix, kind in kinds.items() if relative.lower().endswith(suffix)), "document")
                    )
                )
                entries.append({"id": relative, "path": relative, "kind": kind, "size_bytes": info.file_size})
            return {"entries": entries, "entry_point": job.entry_point}


def output_download(job, output_id, *, storage=None):
    from django.shortcuts import get_object_or_404

    from apps.training.outputs.index import public_outputs

    output = get_object_or_404(public_outputs(job), public_id=output_id)
    if job.outputs_purged_at:
        raise Conflict("Training outputs have been purged.")
    storage = storage or S3Storage()
    bucket, key = storage.parse_uri(output.s3_uri)
    if bucket != storage.bucket or not key.startswith(training_prefix_for(job) + "/"):
        raise Conflict("Training output has an invalid storage scope.")
    return {"download_url": storage.presigned_get(output.s3_uri, public=True)}
