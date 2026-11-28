from celery import shared_task
from django.db import transaction

from apps.training.jobs.storage_scope import training_prefix_for
from common.telemetry.logging import record_transition
from infrastructure.storage import S3Storage


@shared_task(
    name="apps.training.tasks.execute_training_job",
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    soft_time_limit=50,
    time_limit=55,
)
def execute_training_job(self, job_id):
    from apps.observability.execution.reconciliation import reconcile

    return reconcile("training", job_id)


@shared_task(
    name="apps.training.tasks.cancel_training_job",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    soft_time_limit=50,
    time_limit=55,
)
def cancel_training_job(self, job_id):
    from apps.observability.execution.reconciliation import reconcile

    return reconcile("training", job_id)


def confirm_training_cancellation(job_id):
    from apps.observability.lifecycle import record_training_event
    from apps.training.jobs.logs import append_training_log

    from .models import TrainingJob

    with transaction.atomic():
        try:
            job = TrainingJob.objects.select_for_update().get(public_id=job_id)
        except TrainingJob.DoesNotExist:
            return
        if job.status != "cancelled":
            job.mark_finished("cancelled")
            job.deletion_error = ""
            job.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "runtime_seconds",
                    "deletion_error",
                    "updated_at",
                ]
            )
            record_training_event(
                job=job,
                event_type="cancelled",
                message="Training runtime cancellation confirmed.",
            )
            record_transition(job, "cancelled")
        should_delete = bool(job.deletion_requested_at)
        if should_delete:
            transaction.on_commit(lambda: delete_training_job.delay(str(job.public_id)))
    append_training_log(job_id, "[SYSTEM] Training runtime cancellation confirmed.")


@shared_task(
    name="apps.training.tasks.delete_training_job",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    reject_on_worker_lost=True,
)
def delete_training_job(self, job_id):
    from apps.deployment.builds.cleanup import cleanup_build_for_deletion
    from apps.deployment.builds.submission import request_build_deletion
    from apps.deployment.models import Build
    from apps.training.jobs.logs import delete_training_logs

    from .models import TrainingJob

    try:
        job = TrainingJob.objects.select_related("project", "project__owner").get(public_id=job_id)
    except TrainingJob.DoesNotExist:
        return "deleted"
    if not job.deletion_requested_at:
        return "retained"
    if job.status in {"pending", "queued", "uploading", "running", "cancelling"}:
        return "waiting-for-cancellation"
    from django.conf import settings

    if settings.TRAINING_EXECUTION_WATCH_ENABLED and job.observation_status == "cleanup_pending":
        return "waiting-for-runtime-cleanup"
    from apps.training.resources.models import LocalTrainingReservation, TrainingQuotaReservation

    if (
        TrainingQuotaReservation.objects.filter(job_id=job.public_id, active=True).exists()
        or LocalTrainingReservation.objects.filter(job_id=job.public_id, active=True).exists()
    ):
        return "waiting-for-quota-release"
    if job.builds.exclude(status__in=("failed", "cancelled")).exists() or job.registered_versions.exists():
        TrainingJob.objects.filter(pk=job.pk).update(
            deletion_error="Delete the model version or build referencing this training job first."
        )
        return "blocked-by-build"

    try:
        for build in job.builds.filter(status__in=("failed", "cancelled")):
            try:
                request_build_deletion(build, enqueue=False)
            except Build.DoesNotExist:
                continue
            cleanup_build_for_deletion(str(build.public_id))

        if job.builds.exists():
            return "waiting-for-build-cleanup"

        storage = S3Storage()
        storage.delete_prefix(f"{training_prefix_for(job)}/")
        delete_training_logs(job.public_id)
        job.delete()
        record_transition(job, "deleted")
    except Exception as exc:
        TrainingJob.objects.filter(pk=job.pk).update(deletion_error=str(exc)[:12000])
        raise
    return "deleted"
