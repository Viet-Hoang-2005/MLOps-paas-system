
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.observability.services.lifecycle import record_training_event
from apps.training.models import TrainingJob
from apps.training.tasks import (
    cancel_training_job,
    delete_training_job,
    execute_training_job,
    purge_training_job_outputs,
)
from common.api.exceptions import Conflict

ACTIVE_STATUSES = {"pending", "queued", "uploading", "running", "cancelling"}


def create_job(*, owner, validated_data=None):
    from .drafts import create_draft
    return create_draft(owner=owner, values=validated_data)


def retry_job(job, *, creation_key, storage=None):
    from .drafts import clone_draft
    return clone_draft(job, creation_key=creation_key, retry=True, storage=storage)


def submit_job(job, *, revision, run_key, storage=None):
    from .drafts import submit_draft
    return submit_draft(job, revision=revision, run_key=run_key, storage=storage)


@transaction.atomic
def _submit_job_atomic(job, *, verified_gpu_id, local_capacity=None):
    if job.backend == "argo":
        from apps.training.services.quota import lock_owner
        lock_owner(job.owner_id)
    from apps.catalog.models import ModelProject
    project = ModelProject.objects.select_for_update().filter(pk=job.project_id).first() if job.project_id else None
    job = TrainingJob.objects.select_for_update().get(pk=job.pk)
    from apps.training.services.resources import validate_resources
    validate_resources({}, job, local_capacity=local_capacity)
    if settings.TRAINING_BACKEND == "docker" and job.accelerator_type == "gpu" and job.local_gpu_id != verified_gpu_id:
        raise Conflict("The selected GPU changed; retry the request.")
    if project and project.deletion_state != "active":
        raise Conflict("This project is being deleted.")
    if job.deletion_requested_at:
        raise Conflict("This training job is being deleted.")
    if job.status != "pending" or job.submitted_at is not None:
        raise Conflict("Only pending jobs can be submitted.")
    if job.backend == "argo":
        from apps.training.services.quota import reserve
        reserve(job)
    elif job.backend == "docker":
        from apps.training.services.local_resources import reserve
        reserve(job, local_capacity)
    job.status = "queued"
    job.submitted_at = timezone.now()
    job.save(update_fields=["status", "submitted_at", "dispatch_deadline_at", "updated_at"])
    transaction.on_commit(lambda: _enqueue(job))
    return job


def _enqueue(job):
    from apps.observability.services.executions import enqueue_safely
    enqueue_safely(job, execute_training_job)


def cancel_job(job):
    with transaction.atomic():
        job = type(job).objects.select_for_update().get(pk=job.pk)
        if job.status in {"completed", "failed", "cancelled"}:
            return job
        if not job.submitted_at:
            raise Conflict("This job has no submitted runtime to cancel.")
        job.status = "cancelling"
        job.deletion_error = ""
        job.save(update_fields=["status", "deletion_error", "updated_at"])
        job.capabilities.filter(purpose="tracking").delete()
        record_training_event(
            job=job,
            event_type="cancellation_requested",
            message="Training cancellation requested.",
        )
        from apps.observability.services.executions import enqueue_safely
        transaction.on_commit(lambda: enqueue_safely(job, cancel_training_job))
    return job


def request_job_deletion(job):
    with transaction.atomic():
        job = type(job).objects.select_for_update().get(pk=job.pk)
        if job.builds.filter(status__in=("pending", "queued", "building")).exists():
            raise Conflict("A model build is still using this training output.")

        retrying = bool(job.deletion_requested_at and job.deletion_error)
        if job.deletion_requested_at and not retrying:
            return job

        job.deletion_requested_at = timezone.now()
        job.deletion_error = ""
        job.capabilities.filter(purpose="tracking").delete()
        if not job.submitted_at:
            job.status = "editing"
            job.submission_token = None
            job.save(update_fields=["status", "submission_token"])
        if job.submitted_at and job.status in ACTIVE_STATUSES:
            job.status = "cancelling"
            task = cancel_training_job
            event_type = "delete_cancellation_requested"
            message = "Training deletion requested; runtime cancellation started."
        else:
            task = delete_training_job
            event_type = "deletion_requested"
            message = "Training deletion requested."
        if settings.TRAINING_EXECUTION_WATCH_ENABLED and job.submitted_at:
            job.execution_stop_requested = True
            job.observation_status = "cleanup_pending"
            job.next_execution_check_at = timezone.now()
            task = cancel_training_job
        job.save(
            update_fields=[
                "deletion_requested_at",
                "deletion_error",
                "status",
                "execution_stop_requested",
                "observation_status",
                "next_execution_check_at",
                "updated_at",
            ]
        )
        record_training_event(job=job, event_type=event_type, message=message)
        from apps.observability.services.executions import enqueue_safely
        transaction.on_commit(lambda: enqueue_safely(job, task))
    return job


def request_output_purge(job):
    with transaction.atomic():
        job = type(job).objects.select_for_update().get(pk=job.pk)
        if job.outputs_purged_at is not None:
            return job
        if job.status != "completed" or not job.outputs.exists():
            raise Conflict("This training job has no completed output to delete.")
        if job.builds.filter(status__in=("pending", "queued", "building")).exists():
            raise Conflict("Training output is being used by an active model build.")
        job.outputs_purged_at = timezone.now()
        job.artifact_selection = {}
        job.output_revision += 1
        job.save(update_fields=["outputs_purged_at", "artifact_selection", "output_revision", "updated_at"])
        record_training_event(
            job=job,
            event_type="outputs_purge_requested",
            message="Training output deletion requested.",
        )
        transaction.on_commit(lambda: purge_training_job_outputs.delay(str(job.public_id)))
    return job

