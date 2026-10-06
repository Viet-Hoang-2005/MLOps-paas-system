import uuid

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor
from apps.registry.models import ModelArtifact, ModelVersion
from common.api.exceptions import Conflict
from common.validation.artifacts import (
    parse_reference_preview,
    validate_reference_data_file,
)
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import project_prefix, version_prefix

MAX_REFERENCE_BYTES = 100 * 1024 * 1024


def reference_download_url(monitor, storage=None):
    if not monitor.reference_uri:
        raise Conflict("The monitor does not have a reference snapshot.")
    return (storage or S3Storage()).presigned_get(monitor.reference_uri, 900)


def validate_reference_upload(upload):
    try:
        name, _ = validate_reference_data_file(upload)
        upload.seek(0)
        return name
    except ValidationError as exc:
        upload.seek(0)
        if "reference_data_file" in exc.detail:
            raise ValidationError({"reference_file": exc.detail["reference_data_file"]}) from exc
        raise
    except Exception:
        upload.seek(0)
        raise


def get_monitor_reference_preview(monitor, storage=None) -> dict:
    storage = storage or S3Storage()
    if not monitor.reference_uri:
        raise ValidationError({"reference_file": "This monitor does not have a reference snapshot."})
    try:
        raw = storage.read(monitor.reference_uri)
    except Exception as exc:
        raise ValidationError({"reference_file": "Could not read reference data from storage."}) from exc
    return parse_reference_preview(raw, monitor.reference_name or "reference.csv", max_rows=100)


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
                name, fmt = validate_reference_data_file(upload)
                content_type = "text/csv" if fmt == "csv" else "application/vnd.apache.parquet"
                key = (
                    f"{version_prefix(project.owner.tenant_id, project.public_id, version.public_id)}"
                    f"/artifacts/reference_data/{public_id}/{name}"
                )
                stored = storage.put(key, upload, content_type)
                written.append(stored.uri)
                artifact = ModelArtifact.objects.create(
                    version=version,
                    kind="reference_data",
                    name=name,
                    uri=stored.uri,
                    checksum=stored.checksum,
                    size_bytes=stored.size_bytes,
                    content_type=content_type,
                    metadata={"source": "drift_monitor", "monitor_id": str(public_id), "format": fmt},
                )
            if not artifact:
                raise ValidationError({"reference_file": "A reference CSV or Parquet file is required."})
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

