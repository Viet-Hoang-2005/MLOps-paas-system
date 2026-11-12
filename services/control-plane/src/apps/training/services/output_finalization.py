"""Asynchronous output publication shared by trusted callbacks and observers."""

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.training.models import TrainingJob


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=None,
    acks_late=True,
    reject_on_worker_lost=True,
)
def cleanup_output_archive(job_id):
    from infrastructure.storage import S3Storage
    from .storage_scope import validate_training_uri

    job = TrainingJob.objects.filter(public_id=job_id).first()
    if job is None or job.tracking.get("output_contract") != 2:
        return
    if not job.outputs.filter(metadata__group="_mlops", relative_path="_mlops/output_manifest.json").exists():
        return
    storage = S3Storage()
    validate_training_uri(job, storage.bucket, "output", job.output_uri)
    storage.delete(job.output_uri)


def enqueue_output(job, finished_at=None):
    if job.status in {"completed", "failed", "cancelled", "cancelling"} or job.deletion_requested_at:
        return
    now = timezone.now()
    previous = job.tracking.get("output_index_queued_at")
    if finished_at:
        job.tracking = {**job.tracking, "output_runtime_finished_at": finished_at.isoformat()}
        job.save(update_fields=["tracking", "updated_at"])
    if previous and now.timestamp() - float(previous) < 600:
        return
    job.status = "uploading"
    job.tracking = {
        **job.tracking,
        "output_index_queued_at": now.timestamp(),
        "output_runtime_finished_at": job.tracking.get("output_runtime_finished_at")
        or (finished_at or now).isoformat(),
    }
    job.save(update_fields=["status", "tracking", "updated_at"])
    transaction.on_commit(lambda: finalize_output.delay(str(job.public_id)))


@shared_task(
    bind=True, max_retries=5, acks_late=True, reject_on_worker_lost=True, soft_time_limit=3500, time_limit=3600
)
def finalize_output(self, job_id):
    from .outputs import verify_training_output
    from apps.observability.services.lifecycle import record_training_event
    from django.utils.dateparse import parse_datetime

    try:
        job = TrainingJob.objects.get(public_id=job_id)
    except TrainingJob.DoesNotExist:
        return
    if job.status != "uploading" or job.deletion_requested_at:
        return
    error = ""
    try:
        verify_training_output(job)
    except Exception as exc:
        if not isinstance(exc, ValueError) and self.request.retries < self.max_retries:
            raise self.retry(
                exc=RuntimeError("Output indexing temporarily unavailable."), countdown=min(60, 2**self.request.retries)
            ) from exc
        error = "Training Output validation/indexing failed."
    with transaction.atomic():
        current = TrainingJob.objects.select_for_update().get(pk=job.pk)
        if current.status != "uploading" or current.deletion_requested_at:
            return
        current.mark_finished("failed" if error else "completed")
        finished = parse_datetime(current.tracking.get("output_runtime_finished_at", ""))
        if finished:
            current.completed_at = finished
            current.runtime_seconds = max(
                0, int((finished - (current.runtime_started_at or current.started_at or finished)).total_seconds())
            )
        current.error_message = error
        current.execution_stop_requested = True
        current.observation_status = "cleanup_pending"
        current.next_execution_check_at = timezone.now()
        current.save(
            update_fields=[
                "status",
                "completed_at",
                "runtime_seconds",
                "error_message",
                "execution_stop_requested",
                "observation_status",
                "next_execution_check_at",
                "updated_at",
            ]
        )
        record_training_event(
            job=current,
            event_type="output_finalized",
            message=error or "Model/Metadata outputs verified and published.",
        )
        transaction.on_commit(lambda: _notify_result(current))


def _notify_result(job):
    import logging
    from apps.notifications.hooks import notify_training_result
    from common.logging import record_transition

    record_transition(job, job.status, reason=job.error_message or None)
    try:
        notify_training_result(job)
    except Exception:
        logging.getLogger(__name__).exception("Failed to notify training output completion: %s", job.public_id)
