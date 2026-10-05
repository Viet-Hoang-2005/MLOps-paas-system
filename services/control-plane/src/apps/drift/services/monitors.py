import csv
import io
import uuid
from pathlib import Path

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor
from apps.registry.models import ModelArtifact, ModelVersion
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import project_prefix, version_prefix

MAX_REFERENCE_BYTES = 10 * 1024 * 1024


def reference_download_url(monitor, storage=None):
    if not monitor.reference_uri:
        raise Conflict("The monitor does not have a reference snapshot.")
    return (storage or S3Storage()).presigned_get(monitor.reference_uri, 900)


def validate_reference_upload(upload):
    name = Path(upload.name.replace("\\", "/")).name
    if not name.lower().endswith(".csv") or len(name) > 255:
        raise ValidationError({"reference_file": "Upload a CSV file with a valid filename."})
    try:
        content = upload.read(MAX_REFERENCE_BYTES + 1)
        if len(content) > MAX_REFERENCE_BYTES:
            raise ValueError
        text = content.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError
        rows = csv.reader(io.StringIO(text), strict=True)
        header = next(rows)
        if not header or any(not col.strip() for col in header) or len(set(header)) != len(header):
            raise ValueError
        count = 0
        for row in rows:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError
            count += 1
        if not count:
            raise ValueError
    except (ValueError, UnicodeDecodeError, csv.Error, StopIteration) as exc:
        raise ValidationError({"reference_file": "Upload a UTF-8 CSV with a header and data rows, at most 10 MiB."}) from exc
    finally:
        upload.seek(0)
    return name


def create_monitor(*, data, backend, storage=None):
    storage = storage or S3Storage()
    data = dict(data)
    upload = data.pop("reference_file", None)
    version = data["version"]
    written = []
    try:
        with transaction.atomic():
            project = ModelProject.objects.select_for_update().get(pk=version.project_id)
            version = ModelVersion.objects.select_for_update().get(pk=version.pk)
            data["version"] = version
            if not project.is_active or project.deletion_state != "active":
                raise Conflict("This project is being deleted.")
            if (
                not project.active_deployment_id
                or project.active_deployment.version_id != version.pk
                or project.active_deployment.status != "succeeded"
            ):
                raise Conflict("Select the project's Running version. Reload if deployment changed.")
            if DriftMonitor.objects.filter(version=version, name=data.get("name", "")).exists():
                raise Conflict("A monitor with this name already exists for the version.")
            public_id = uuid.uuid4()
            artifact = version.artifacts.filter(kind="reference_data").first()
            if upload and artifact:
                raise Conflict("This version already has reference data. It cannot be replaced from monitoring.")
            if upload:
                name = validate_reference_upload(upload)
                key = (
                    f"{version_prefix(project.owner.tenant_id, project.public_id, version.public_id)}"
                    f"/artifacts/reference_data/{public_id}/{name}"
                )
                stored = storage.put(key, upload, "text/csv")
                written.append(stored.uri)
                artifact = ModelArtifact.objects.create(
                    version=version, kind="reference_data", name=name, uri=stored.uri,
                    checksum=stored.checksum, size_bytes=stored.size_bytes, content_type="text/csv",
                    metadata={"source": "drift_monitor", "monitor_id": str(public_id)},
                )
            if not artifact:
                raise ValidationError({"reference_file": "A reference CSV is required."})
            name = artifact.name
            key = f"{project_prefix(project.owner.tenant_id, project.public_id)}/drift/{public_id}/reference/{name}"
            stored = storage.copy(artifact.uri, key)
            written.append(stored.uri)
            return DriftMonitor.objects.create(
                public_id=public_id, reference_uri=stored.uri, reference_name=name, backend=backend, **data
            )
    except Exception:
        for uri in reversed(written):
            storage.delete(uri)
        raise
