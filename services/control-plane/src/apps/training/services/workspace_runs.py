"""Snapshot an account-owned draft and atomically reserve/submit a fresh run."""
from io import BytesIO
from zipfile import ZipFile

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.training.models import TrainingJob
from apps.training.services import workspaces
from apps.training.services.jobs import submit_job
from apps.training.services.resources import validate_resources
from apps.training.services.storage_scope import expected_training_uris, training_prefix_for
from apps.observability.services.lifecycle import record_training_event
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage


def run_workspace(workspace, *, revision, run_key, values, storage=None):
    existing = TrainingJob.objects.filter(run_key=run_key).first()
    if existing:
        if existing.owner_id != workspace.owner_id or existing.workspace_id != workspace.pk:
            raise Conflict("This run identifier is unavailable.")
        return existing
    capacity = None
    if settings.TRAINING_BACKEND == "docker":
        from apps.training.services.local_resources import require_capacity
        capacity = require_capacity(force=True)
    validate_resources(values, local_capacity=capacity)
    if values.get("accelerator_type") == "gpu" and settings.TRAINING_BACKEND == "docker":
        from apps.training.services.local_gpu import require_device
        require_device(values["local_gpu_id"])
    storage = storage or S3Storage()
    snapshot = workspaces.snapshot_input(workspace, revision=revision, storage=storage)
    with ZipFile(BytesIO(snapshot["archive"])) as archive:
        requirements = archive.read("requirements.txt").decode("utf-8") if "requirements.txt" in archive.namelist() else ""
    job = TrainingJob(owner=workspace.owner, workspace=workspace, workspace_revision=snapshot["revision"],
        run_key=run_key, input_contract="workspace", storage_layout="tenant", backend=settings.TRAINING_BACKEND,
        entry_point=snapshot["entry_point"], requirements_text=requirements, **values)
    uris = expected_training_uris(job, storage.bucket)
    job.code_snapshot_uri, job.data_snapshot_uri = uris["code"], uris["data"]
    job.output_uri, job.mlflow_artifact_uri = uris["output"], uris["mlflow"]
    try:
        storage.put(storage.parse_uri(job.code_snapshot_uri)[1], snapshot["archive"], "application/zip")
        empty = BytesIO()
        with ZipFile(empty, "w"):
            pass
        storage.put(storage.parse_uri(job.data_snapshot_uri)[1], empty.getvalue(), "application/zip")
        with transaction.atomic():
            # Workspace mutation/run admission use the same lock.
            locked = workspaces._lock(workspace, snapshot["revision"])
            job.environment_snapshot = dict(locked.environment)
            job.secret_snapshot = {secret.name: bytes(secret.ciphertext).decode("ascii") for secret in locked.secrets.all()}
            job.save()
            record_training_event(job=job, event_type="created", message="Training run created from workspace snapshot.")
            return submit_job(job, verify_gpu=False, local_capacity=capacity)
    except Exception:
        if not TrainingJob.objects.filter(public_id=job.public_id).exists():
            storage.delete_prefix(training_prefix_for(job) + "/")
        existing = TrainingJob.objects.filter(run_key=run_key, owner=workspace.owner, workspace=workspace).first()
        if existing:
            return existing
        raise


def runtime_configuration(job_id, token):
    from apps.training.services.capabilities import capability_for_token
    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().filter(public_id=job_id).first()
        if job is None:
            raise PermissionDenied("Invalid runtime configuration capability.")
        cap = capability_for_token(job=job, purpose="runtime_config", token=token)
        if not cap or cap.consumed_at or job.status not in {"queued", "running"} or job.execution_stop_requested or job.deletion_requested_at:
            raise PermissionDenied("Invalid runtime configuration capability.")
        if job.project_id and job.project.deletion_state != "active":
            raise PermissionDenied("Training is stopping.")
        values = dict(job.environment_snapshot)
        if job.secret_snapshot:
            cipher = workspaces.cipher()
            values.update({name: cipher.decrypt(value.encode("ascii")).decode("utf-8") for name, value in job.secret_snapshot.items()})
        from django.utils import timezone
        cap.consumed_at = timezone.now()
        cap.save(update_fields=["consumed_at"])
        return {"environment": values, "secret_names": list(job.secret_snapshot)}
