import uuid
from pathlib import Path

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import project_prefix


def create_monitor(*, data, backend, storage=None):
    storage = storage or S3Storage()
    data = dict(data)
    upload = data.pop("reference_file", None)
    version = data["version"]
    with transaction.atomic():
        project = ModelProject.objects.select_for_update().get(pk=version.project_id)
        if not project.is_active or project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        if not project.active_deployment_id or project.active_deployment.version_id != version.pk:
            raise Conflict("Select the project's Running version. Reload if deployment changed.")
        public_id = uuid.uuid4()
        artifact = version.artifacts.filter(kind="reference_data").first()
        name = Path(upload.name).name if upload else artifact.name if artifact else ""
        if not name.lower().endswith(".csv"):
            raise ValidationError({"reference_file": "A reference CSV is required."})
        key = f"{project_prefix(project.owner.tenant_id, project.public_id)}/drift/{public_id}/reference/{name}"
        stored = storage.put(key, upload, "text/csv") if upload else storage.copy(artifact.uri, key)
        try:
            return DriftMonitor.objects.create(
                public_id=public_id, reference_uri=stored.uri, reference_name=name, backend=backend, **data
            )
        except Exception:
            storage.delete(stored.uri)
            raise
