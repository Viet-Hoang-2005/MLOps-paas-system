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


def run_workspace(workspace, *, revision, run_key):
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
        validate_resources({}, job, static_only=True)
        try:
            with transaction.atomic():
                job.save()
        except IntegrityError as exc:
            raise Conflict("This submission key is unavailable or the workspace is busy.") from exc
        locked.save(update_fields=["updated_at"])
        transaction.on_commit(lambda: enqueue_preparation(job.public_id, job.submission_token))
    return job


def enqueue_preparation(job_id, token):
    from apps.training.services.preparation import prepare_training_input

    try:
        prepare_training_input.apply_async(args=[str(job_id), str(token)], retry=False)
    except Exception:
        fail_preparation(job_id, token, "Could not queue Input preparation. Run again from the workspace.")


def fail_preparation(job_id, token, message):
    from .workspace_lifecycle import cleanup_preparation

    with transaction.atomic():
        changed = TrainingJob.objects.filter(
            public_id=job_id, status="pending", submitted_at__isnull=True, submission_token=token,
        ).update(status="failed", completed_at=timezone.now(), submission_token=None, error_message=message)
        if changed:
            transaction.on_commit(lambda: cleanup_preparation.apply_async(
                args=[str(job_id), str(token)], countdown=60, retry=False,
            ), robust=True)


def prepare_workspace(job_id, token, *, storage=None):
    from .jobs import _submit_job_atomic
    from .preparation import PreparationStorage
    from .resources import validate_resources

    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().filter(
            public_id=job_id, status="pending", submitted_at__isnull=True,
            submission_token=token, deletion_requested_at__isnull=True,
        ).first()
        if not job:
            return None
        if not job.preparation_started_at or timezone.now() >= job.preparation_started_at + PREPARATION_LEASE:
            fail_preparation(job_id, token, "Input preparation expired. Run again from the workspace.")
            return None
        job.submission_token = uuid.uuid4()
        job.save(update_fields=["submission_token", "updated_at"])
    locked = job.workspace
    revision = job.input_revision
    token = job.submission_token
    def checkpoint():
        if timezone.now() >= job.preparation_started_at + PREPARATION_LEASE:
            raise TimeoutError("Input preparation expired.")
        if not TrainingJob.objects.filter(
            pk=job.pk, status="pending", submitted_at__isnull=True, submission_token=token,
            deletion_requested_at__isnull=True, workspace__deletion_requested_at__isnull=True,
        ).exists():
            raise Conflict("Input preparation is no longer current.")

    try:
        storage = storage or PreparationStorage(checkpoint)
        checkpoint()
        snapshot = workspaces.snapshot_input(locked, revision=revision, storage=storage, preparing=True, checkpoint=checkpoint)
        checkpoint()
        uris = expected_training_uris(job, storage.bucket)
        with ZipFile(BytesIO(snapshot["archive"])) as archive:
            requirements = archive.read("requirements.txt").decode("utf-8") if "requirements.txt" in archive.namelist() else ""
        storage.put(storage.parse_uri(uris["code"])[1], snapshot["archive"], "application/zip")
        checkpoint()
        empty = BytesIO()
        with ZipFile(empty, "w"):
            pass
        storage.put(storage.parse_uri(uris["data"])[1], empty.getvalue(), "application/zip")
        checkpoint()
        capacity = None
        if job.backend == "docker":
            from .local_resources import require_capacity
            capacity = require_capacity(force=True)
        validate_resources({}, job, local_capacity=capacity)
        verified_gpu_id = ""
        if job.backend == "docker" and job.accelerator_type == "gpu":
            from .local_gpu import require_device
            require_device(job.local_gpu_id)
            verified_gpu_id = job.local_gpu_id
        with transaction.atomic():
            current_workspace = TrainingWorkspace.objects.select_for_update().get(pk=locked.pk)
            current = TrainingJob.objects.select_for_update().get(pk=job.pk)
            checkpoint()
            if current_workspace.revision != revision or current.owner_id != current_workspace.owner_id:
                raise Conflict("The preparation is no longer current.")
            current.requirements_text = requirements
            current.code_snapshot_uri, current.data_snapshot_uri = uris["code"], uris["data"]
            current.output_uri, current.mlflow_artifact_uri = uris["output"], uris["mlflow"]
            current.save()
            return _submit_job_atomic(current, verified_gpu_id=verified_gpu_id, local_capacity=capacity)
    except Exception:
        accepted = TrainingJob.objects.filter(pk=job.pk, submitted_at__isnull=False).exists()
        if not accepted:
            fail_preparation(job_id, token, "Input preparation or admission failed. Run again from the workspace.")
            if storage:
                # A cancelled/deleted job must not leave objects uploaded after its cleanup.
                try:
                    storage.delete_prefix(f"{training_prefix_for(job)}/input/submissions/{token}/")
                except Exception:
                    from .workspace_lifecycle import cleanup_preparation
                    # Carry the trusted prefix so deletion of the DB row cannot strand late uploads.
                    transaction.on_commit(lambda: cleanup_preparation.apply_async(
                        args=[str(job_id), str(token), f"{training_prefix_for(job)}/input/submissions/{token}/"],
                        countdown=60, retry=False,
                    ), robust=True)
        raise
