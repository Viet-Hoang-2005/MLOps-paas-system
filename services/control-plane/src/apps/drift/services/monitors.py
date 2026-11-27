import uuid

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor
from apps.registry.models import ModelArtifact, ModelVersion
from common.api.exceptions import Conflict
from common.validation.artifacts import (
    MAX_REFERENCE_DATA_BYTES,
    parse_reference_preview,
    validate_reference_data_file,
)
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import version_prefix
from infrastructure.storage.staged_csv import resolve_csv_upload

MAX_REFERENCE_BYTES = 100 * 1024 * 1024


def reference_download_url(monitor, storage=None):
    if not monitor.reference_uri:
        raise Conflict("The monitor does not have a reference snapshot.")
    return (storage or S3Storage()).presigned_get(monitor.reference_uri, 900, public=True)


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
        raw = storage.read(monitor.reference_uri, max_bytes=MAX_REFERENCE_DATA_BYTES)
    except Exception as exc:
        raise ValidationError({"reference_file": "Could not read reference data from storage."}) from exc
    return parse_reference_preview(raw, monitor.reference_name or "reference.csv", max_rows=100)


def _validate_monitor_target(project, version, data, *, upload):
    if not project.is_active or project.deletion_state != "active":
        raise Conflict("This project is being deleted.")
    if version.deletion_requested:
        raise Conflict("This model version is being deleted.")
    if (
        not project.active_deployment_id
        or project.active_deployment.version_id != version.pk
        or project.active_deployment.status != "succeeded"
    ):
        raise Conflict("Select the project's Running version. Reload if deployment changed.")
    if DriftMonitor.objects.filter(version=version, name=data.get("name", "")).exists():
        raise Conflict("A monitor with this name already exists for the version.")
    artifact = version.artifacts.filter(kind="reference_data").first()
    if upload and artifact:
        raise Conflict("This version already has reference data. It cannot be replaced from monitoring.")
    if not upload and not artifact:
        raise ValidationError({"reference_file": "A reference CSV file is required."})
    return artifact


def create_monitor(*, data, backend, storage=None):
    storage = storage or S3Storage()
    data = dict(data)
    upload = data.pop("reference_file", None)
    version = data["version"]
    staged_csv = None
    if "csv_upload_token" in data:
        if upload is not None:
            raise ValidationError({"reference_file": "Send either a CSV file or an upload token."})
        staged_csv = resolve_csv_upload(data.pop("csv_upload_token"), version, "drift-monitor", error_field="reference_file")
    has_upload = bool(upload or staged_csv)
    written = []
    public_id = uuid.uuid4()
    upload_name = None
    upload_key = None
    stored = None
    try:
        if upload:
            upload_name, _ = validate_reference_data_file(upload)
        elif staged_csv:
            upload_name = staged_csv.filename
        with transaction.atomic():
            project = ModelProject.objects.select_for_update().get(pk=version.project_id)
            version = ModelVersion.objects.select_for_update().get(pk=version.pk)
            _validate_monitor_target(project, version, data, upload=has_upload)
            if has_upload:
                upload_key = (
                    f"{version_prefix(project.owner.tenant_id, project.public_id, version.public_id)}"
                    f"/artifacts/reference_data/{public_id}/{upload_name}"
                )
        if upload_key:
            stored = staged_csv.promote(storage, upload_key) if staged_csv else storage.put(upload_key, upload, "text/csv")
            written.append(stored.uri)
        with transaction.atomic():
            project = ModelProject.objects.select_for_update().get(pk=version.project_id)
            version = ModelVersion.objects.select_for_update().get(pk=version.pk)
            data["version"] = version
            artifact = _validate_monitor_target(project, version, data, upload=has_upload)
            if stored:
                artifact = ModelArtifact.objects.create(
                    version=version,
                    kind="reference_data",
                    name=upload_name,
                    uri=stored.uri,
                    checksum=stored.checksum,
                    size_bytes=stored.size_bytes,
                    content_type="text/csv",
                    metadata={"source": "drift_monitor", "monitor_id": str(public_id), "format": "csv"},
                )
            return DriftMonitor.objects.create(
                public_id=public_id, reference_uri=artifact.uri, reference_name=artifact.name, backend=backend, **data
            )
    except Exception:
        for uri in reversed(written):
            storage.delete(uri)
        raise
