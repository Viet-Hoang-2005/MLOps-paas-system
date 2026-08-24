from celery import shared_task
from django.db import transaction
from infrastructure.execution import training_backend
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import (
    training_job_prefix,
    training_mlflow_prefix,
    training_output_prefix,
)


@shared_task(
    bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_jitter=True, max_retries=5
)
def execute_training_job(self, job_id):
    from .models import TrainingJob, TrainingJobEvent
    from .services.logs import append_training_log

    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().select_related("project", "project__owner").get(public_id=job_id)
        if job.status != "queued" or job.deletion_requested_at:
            return job.status
        job.mark_started()
        job.celery_task_id = self.request.id or job.celery_task_id
        job.error_message = ""
        job.save(update_fields=["status", "started_at", "celery_task_id", "error_message", "updated_at"])
        TrainingJobEvent.objects.create(job=job, event_type="started", message="Training execution started.")
    append_training_log(job.public_id, "[SYSTEM] Training execution started.")
    with transaction.atomic():
        job = (
            TrainingJob.objects.select_for_update()
            .select_related("project", "project__owner")
            .get(pk=job.pk)
        )
        if job.status in {"cancelling", "cancelled"} or job.deletion_requested_at:
            should_confirm = job.status == "cancelling"
        else:
            should_confirm = False
    if should_confirm:
        confirm_training_cancellation(job_id)
        return "cancelled"
    try:
        append_training_log(job.public_id, f"[SYSTEM] Dispatching {job.backend} training backend.")
        result = training_backend(job.backend).run(job)
    except Exception as exc:
        with transaction.atomic():
            job = TrainingJob.objects.select_for_update().get(pk=job.pk)
            if job.status in {"cancelling", "cancelled"} or job.deletion_requested_at:
                append_training_log(job.public_id, "[SYSTEM] Training stopped by cancellation.")
                return job.status
            job.mark_finished("failed")
            job.error_message = str(exc)[:12000]
            job.save(update_fields=["status", "completed_at", "runtime_seconds", "error_message", "updated_at"])
            TrainingJobEvent.objects.create(
                job=job, event_type="failed", message="Training execution failed.", metadata={"error": str(exc)[:1000]}
            )
        append_training_log(job.public_id, f"[ERROR] Training failed: {exc}")
        raise
    if isinstance(result, dict) and result.get("dispatched"):
        append_training_log(job.public_id, "[SYSTEM] Training workload dispatched; waiting for trusted callback.")
        return "running"
    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().get(pk=job.pk)
        if job.status in {"cancelling", "cancelled"} or job.deletion_requested_at:
            append_training_log(job.public_id, "[SYSTEM] Ignoring completion after cancellation.")
            return job.status
        job.mark_finished("completed")
        job.tracking = {**job.tracking, "logs_tail": str(result)[-6000:]}
        job.save(update_fields=["status", "completed_at", "runtime_seconds", "tracking", "updated_at"])
        job.outputs.update_or_create(
            relative_path="model.tar.gz",
            defaults={"kind": "model", "s3_uri": job.output_uri, "content_type": "application/gzip"},
        )
        TrainingJobEvent.objects.create(job=job, event_type="completed", message="Training execution completed.")
    for line in str(result).splitlines()[-500:]:
        append_training_log(job.public_id, line)
    append_training_log(job.public_id, "[SYSTEM] Training completed successfully.")
    return "completed"


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def cancel_training_job(self, job_id):
    from .models import TrainingJob
    from .services.logs import append_training_log

    try:
        job = TrainingJob.objects.select_related("project", "project__owner").get(public_id=job_id)
    except TrainingJob.DoesNotExist:
        return "deleted"
    if job.celery_task_id:
        self.app.control.revoke(job.celery_task_id, terminate=False)
    try:
        result = training_backend(job.backend).cancel(job)
    except Exception as exc:
        TrainingJob.objects.filter(pk=job.pk).update(deletion_error=str(exc)[:12000])
        append_training_log(job.public_id, f"[ERROR] Training cancellation failed: {exc}")
        raise
    if isinstance(result, dict):
        if result.get("retry"):
            raise RuntimeError(
                result.get("detail")
                or "Training runtime is not registered yet; cancellation will be retried."
            )
        if result.get("dispatched"):
            append_training_log(
                job.public_id,
                "[SYSTEM] Runtime cancellation dispatched; waiting for confirmation.",
            )
            return "cancelling"
    confirm_training_cancellation(job_id)
    return "cancelled"


def confirm_training_cancellation(job_id):
    from .models import TrainingJob, TrainingJobEvent
    from .services.logs import append_training_log

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
            TrainingJobEvent.objects.create(
                job=job,
                event_type="cancelled",
                message="Training runtime cancellation confirmed.",
            )
        should_delete = bool(job.deletion_requested_at)
        if should_delete:
            transaction.on_commit(lambda: delete_training_job.delay(str(job.public_id)))
    append_training_log(job_id, "[SYSTEM] Training runtime cancellation confirmed.")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def delete_training_job(self, job_id):
    from apps.deployment.models import Build
    from apps.deployment.tasks import cleanup_failed_build_artifacts

    from .models import TrainingJob
    from .services.logs import delete_training_logs

    try:
        job = (
            TrainingJob.objects.select_related("project", "project__owner")
            .prefetch_related("builds")
            .get(public_id=job_id)
        )
    except TrainingJob.DoesNotExist:
        return "deleted"
    if not job.deletion_requested_at:
        return "retained"
    if job.status in {"pending", "queued", "uploading", "running", "cancelling"}:
        return "waiting-for-cancellation"
    if job.builds.filter(status__in=("pending", "queued", "building")).exists():
        TrainingJob.objects.filter(pk=job.pk).update(
            deletion_error="A model build is still using this training output."
        )
        return "blocked-by-build"

    try:
        disposable_builds = list(
            job.builds.filter(status__in=("failed", "cancelled")).values_list(
                "public_id", flat=True
            )
        )
        for build_id in disposable_builds:
            cleanup_failed_build_artifacts.run(str(build_id), True)
        Build.objects.filter(public_id__in=disposable_builds).delete()

        storage = S3Storage()
        storage.delete_prefix(
            f"{training_job_prefix(job.project.owner.tenant_id, job.project.public_id, job.public_id)}/"
        )
        delete_training_logs(job.public_id)
        job.delete()
    except Exception as exc:
        TrainingJob.objects.filter(pk=job.pk).update(deletion_error=str(exc)[:12000])
        raise
    return "deleted"


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def purge_training_job_outputs(self, job_id):
    from .models import TrainingJob, TrainingJobEvent

    job = TrainingJob.objects.select_related("project", "project__owner").get(public_id=job_id)
    storage = S3Storage()
    tenant_id = job.project.owner.tenant_id
    project_id = job.project.public_id
    storage.delete_prefix(training_output_prefix(tenant_id, project_id, job.public_id))
    storage.delete_prefix(training_mlflow_prefix(tenant_id, project_id, job.public_id))
    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().get(pk=job.pk)
        job.outputs.all().delete()
        TrainingJobEvent.objects.create(
            job=job,
            event_type="outputs_purged",
            message="Training outputs were deleted.",
        )
    return "purged"
