"""Publish only verified Model/Metadata files from the private v2 package."""

import hashlib
import json
import mimetypes
import tarfile
import uuid
from contextlib import closing
from pathlib import PurePosixPath
from tempfile import SpooledTemporaryFile

from django.db import transaction
from django.db.models import Q

from apps.training.models import TrainingJob, TrainingOutput
from .storage_scope import training_prefix_for, validate_training_uri

MODEL_EXTENSIONS = {
    "sklearn": {".pkl", ".joblib"},
    "xgboost": {".pkl", ".joblib"},
    "pytorch": {".pt", ".pth"},
    "tensorflow": {".h5", ".keras"},
    "keras": {".h5", ".keras"},
}
METADATA_EXTENSIONS = {".json", ".csv", ".txt", ".md", ".png", ".jpg", ".jpeg", ".pdf"}


def public_outputs(job):
    if job.outputs_purged_at or job.deletion_requested_at:
        return job.outputs.none()
    return job.outputs.filter(
        Q(metadata__group="model", relative_path__startswith="Model/")
        | Q(metadata__group="metadata", relative_path__startswith="Metadata/"),
        metadata__contract=2,
    )


def index_output(job, storage):
    if job.tracking.get("output_contract") == 2:
        return
    validate_training_uri(job, storage.bucket, "output", job.output_uri)
    stream, _, _ = storage.open_stream(job.output_uri)
    prefix = training_prefix_for(job) + "/output/files/"
    attempt = uuid.uuid4()
    rows, expected, seen, uploaded = [], {}, set(), []
    totals = {"model": 0, "metadata": 0, "_mlops": 0}
    manifest = None
    try:
        with closing(stream), tarfile.open(fileobj=stream, mode="r|gz") as archive:
            for member in archive:
                name = member.name
                parts = name.split("/")
                if (
                    name in seen
                    or len(seen) >= 20_100
                    or len(parts) < 2
                    or any(p in {"", ".", ".."} or ":" in p for p in parts)
                    or "\\" in name
                    or "\x00" in name
                    or not member.isfile()
                ):
                    raise ValueError("Unsafe output archive entry.")
                seen.add(name)
                group = parts[0]
                if group not in totals or "_mlops" in parts[1:]:
                    raise ValueError("Unsupported output archive namespace.")
                totals[group] += member.size
                if (
                    member.size < 0
                    or totals[group]
                    > {"model": 20 * 1024**3, "metadata": 512 * 1024**2, "_mlops": 512 * 1024**2}[group]
                ):
                    raise ValueError("Output exceeds size limits.")
                if group == "_mlops":
                    if name == "_mlops/output_manifest.json":
                        if member.size > 16 * 1024**2:
                            raise ValueError("Manifest too large.")
                        manifest = json.load(archive.extractfile(member))
                    continue
                suffix = PurePosixPath(name).suffix.lower()
                if group == "model" and member.size == 0:
                    raise ValueError("Model files must not be empty.")
                if suffix not in (MODEL_EXTENSIONS[job.model_flavor] if group == "model" else METADATA_EXTENSIONS):
                    raise ValueError("Unsupported output file format.")
                if group == "metadata" and member.size > 100 * 1024**2:
                    raise ValueError("Metadata file exceeds 100 MiB.")
                digest = hashlib.sha256()
                with SpooledTemporaryFile(max_size=8 * 1024**2, mode="w+b") as payload:
                    source = archive.extractfile(member)
                    copied = 0
                    for chunk in iter(lambda source=source: source.read(1024**2), b""):
                        copied += len(chunk)
                        if copied > member.size:
                            raise ValueError("Invalid output size.")
                        payload.write(chunk)
                        digest.update(chunk)
                    if copied != member.size:
                        raise ValueError("Truncated output file.")
                    checksum = digest.hexdigest()
                    identifier = uuid.uuid5(job.public_id, name + ":" + checksum)
                    payload.seek(0)
                    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
                    # Isolate concurrent attempts: a losing/cancelled task must not
                    # delete the immutable object a winning task has published.
                    stored = storage.upload_fileobj(
                        payload, prefix + f"{identifier}/{attempt}", content_type, checksum=checksum, size_bytes=copied
                    )
                    uploaded.append(stored.uri)
                    rows.append(
                        TrainingOutput(
                            public_id=identifier,
                            job=job,
                            kind="model" if group == "model" else "file",
                            relative_path=("Model/" if group == "model" else "Metadata/") + "/".join(parts[1:]),
                            s3_uri=stored.uri,
                            checksum=checksum,
                            size_bytes=copied,
                            content_type=content_type,
                            metadata={"contract": 2, "group": group},
                        )
                    )
                    expected[name] = {"path": name, "group": group, "checksum": checksum, "size_bytes": copied}
        if not manifest or manifest.get("version") != 2 or manifest.get("framework") != job.model_flavor:
            raise ValueError("Only Output contract v2 is supported.")
        declared = manifest.get("files")
        if (
            not isinstance(declared, list)
            or len(declared) != len(expected)
            or any(not isinstance(v, dict) or not isinstance(v.get("path"), str) for v in declared)
            or {v["path"]: v for v in declared} != expected
        ):
            raise ValueError("Output manifest does not match archive contents.")
        if not any(row.kind == "model" for row in rows) or len(rows) > 20_000:
            raise ValueError("Output requires at least one model and at most 20000 files.")
        with transaction.atomic():
            current = TrainingJob.objects.select_for_update().get(pk=job.pk)
            if (
                current.outputs_purged_at
                or current.deletion_requested_at
                or current.status in {"cancelled", "cancelling", "failed"}
            ):
                raise ValueError("Job no longer accepts output publication.")
            if current.tracking.get("output_contract") != 2:
                TrainingOutput.objects.bulk_create(rows)
                current.tracking = {**current.tracking, "output_contract": 2}
                current.save(update_fields=["tracking", "updated_at"])
            job.tracking = current.tracking
        for uri in uploaded:
            if not TrainingOutput.objects.filter(job=job, s3_uri=uri).exists():
                storage.delete(uri)
    except BaseException:
        # Never remove an object another successful indexer has published.
        for uri in uploaded:
            if not TrainingOutput.objects.filter(job=job, s3_uri=uri).exists():
                storage.delete(uri)
        raise
