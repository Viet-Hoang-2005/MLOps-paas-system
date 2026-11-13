"""Revision-fenced workspace snapshots; every run has its own identity."""

import uuid
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.training.models import TrainingJob, TrainingWorkspace
from apps.training.services import workspaces
from apps.training.services.storage_scope import expected_training_uris, training_prefix_for
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage

CONFIG_FIELDS = (
    "model_flavor",
    "entry_point",
    "vcpu",
    "memory_mb",
    "max_runtime_seconds",
    "accelerator_type",
    "accelerator_count",
    "accelerator_model",
    "local_gpu_id",
)
PREPARATION_LEASE = timedelta(minutes=10)


def create_workspace(*, owner, values=None):
    with transaction.atomic():
        workspace = TrainingWorkspace.objects.create(owner=owner)
        if values:
            workspace = workspaces.update_workspace(
                workspace,
                revision=workspace.revision,
                changes={key: value for key, value in values.items() if key != "revision"},
            )
        return workspace


def recover_preparations():
    from .workspace_lifecycle import cleanup_preparation

    stale = list(
        TrainingJob.objects.filter(
            status="pending",
            submitted_at__isnull=True,
            preparation_started_at__lt=timezone.now() - PREPARATION_LEASE,
            deletion_requested_at__isnull=True,
        ).values_list("pk", "public_id", "submission_token")
    )
    recovered = 0
    for pk, public_id, token in stale:
        with transaction.atomic():
            changed = TrainingJob.objects.filter(
                pk=pk, status="pending", submitted_at__isnull=True, submission_token=token
            ).update(
                status="failed",
                submission_token=None,
                preparation_started_at=None,
                completed_at=timezone.now(),
                error_message="Preparation interrupted. Run again from the workspace.",
            )
            recovered += changed
            if changed and token:
                transaction.on_commit(
                    lambda public_id=public_id, token=token: cleanup_preparation.apply_async(
                        args=[str(public_id), str(token)], countdown=60
                    )
                )
    return recovered


def run_workspace(workspace, *, revision, run_key, storage=None):
    from apps.training.services.jobs import _submit_job_atomic
    from apps.training.services.resources import validate_resources

    with transaction.atomic():
        locked = TrainingWorkspace.objects.select_for_update().get(pk=workspace.pk)
        previous = TrainingJob.objects.filter(run_key=run_key).first()
        if previous:
            if previous.workspace_id != locked.pk or previous.owner_id != locked.owner_id:
                raise Conflict("This submission key is unavailable.")
            return previous
        workspaces._lock(locked, revision)
        if (
            not locked.entry_point
            or not locked.entries.filter(relative_path=locked.entry_point, kind="script").exists()
        ):
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"entry_point": "Select a Python entry point before running training."})
        capacity = None
        if settings.TRAINING_BACKEND == "docker":
            from apps.training.services.local_resources import require_capacity

            capacity = require_capacity(force=True)
        job = TrainingJob(
            workspace=locked,
            owner=locked.owner,
            backend=settings.TRAINING_BACKEND,
            storage_layout="tenant",
            input_revision=locked.revision,
            environment_snapshot=dict(locked.environment),
            secret_snapshot={s.name: bytes(s.ciphertext).decode("ascii") for s in locked.secrets.all()},
            run_key=run_key,
            submission_token=uuid.uuid4(),
            preparation_started_at=timezone.now(),
            **{field: getattr(locked, field) for field in CONFIG_FIELDS},
        )
        validate_resources({}, job, local_capacity=capacity)
        verified_gpu_id = ""
        if job.backend == "docker" and job.accelerator_type == "gpu":
            from apps.training.services.local_gpu import require_device

            require_device(job.local_gpu_id)
            verified_gpu_id = job.local_gpu_id
        try:
            with transaction.atomic():
                job.save()
        except IntegrityError as exc:
            raise Conflict("This submission key is unavailable or the workspace is busy.") from exc
        locked.save(update_fields=["updated_at"])
    try:
        storage = storage or S3Storage()
        snapshot = workspaces.snapshot_input(locked, revision=revision, storage=storage, preparing=True)
        uris = expected_training_uris(job, storage.bucket)
        with ZipFile(BytesIO(snapshot["archive"])) as archive:
            requirements = (
                archive.read("requirements.txt").decode("utf-8") if "requirements.txt" in archive.namelist() else ""
            )
        storage.put(storage.parse_uri(uris["code"])[1], snapshot["archive"], "application/zip")
        empty = BytesIO()
        with ZipFile(empty, "w"):
            pass
        storage.put(storage.parse_uri(uris["data"])[1], empty.getvalue(), "application/zip")
        with transaction.atomic():
            current_workspace = TrainingWorkspace.objects.select_for_update().get(pk=locked.pk)
            current = TrainingJob.objects.select_for_update().get(pk=job.pk)
            if (
                current.status != "pending"
                or current.submission_token != job.submission_token
                or current_workspace.revision != revision
                or current_workspace.deletion_requested_at
                or current.deletion_requested_at
                or current.submitted_at
            ):
                raise Conflict("The preparation is no longer current.")
            current.requirements_text = requirements
            current.code_snapshot_uri, current.data_snapshot_uri = uris["code"], uris["data"]
            current.output_uri, current.mlflow_artifact_uri = uris["output"], uris["mlflow"]
            current.save()
            return _submit_job_atomic(current, verified_gpu_id=verified_gpu_id, local_capacity=capacity)
    except Exception:
        with transaction.atomic():
            current = TrainingJob.objects.select_for_update().filter(pk=job.pk).first()
            accepted = current is not None and current.submitted_at is not None
            if current and not accepted and current.submission_token == job.submission_token:
                current.status = "failed"
                current.completed_at = timezone.now()
                current.error_message = "Input preparation or admission failed. Run again from the workspace."
                current.submission_token = None
                current.save(
                    update_fields=["status", "completed_at", "error_message", "submission_token", "updated_at"]
                )
        if not accepted and storage:
            storage.delete_prefix(f"{training_prefix_for(job)}/input/submissions/{job.submission_token}/")
        raise
