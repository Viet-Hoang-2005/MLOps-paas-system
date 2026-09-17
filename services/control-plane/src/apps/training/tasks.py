from celery import shared_task
from common.logging import record_transition
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
    from apps.observability.services.lifecycle import record_training_event
    from .models import TrainingJob
    from .services.logs import append_training_log

    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().select_related("project", "project__owner").get(public_id=job_id)
        if job.status != "queued" or job.deletion_requested_at:
            return job.status
        job.mark_started()
        job.celery_task_id = self.request.id or job.celery_task_id
        job.error_message = ""
        job.save(update_fields=["status", "started_at", "celery_task_id", "error_message", "updated_at"])
        record_training_event(job=job, event_type="started", message="Training execution started.")
        record_transition(job, "running")
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
            record_training_event(
                job=job, event_type="failed", message="Training execution failed.", metadata={"error": str(exc)[:1000]}
            )
        record_transition(
            job, "failed", reason="Training backend execution failed", error_type=type(exc).__name__, exc_info=True,
        )
        append_training_log(job.public_id, f"[ERROR] Training failed: {exc}")
        raise
    if isinstance(result, dict) and result.get("dispatched"):
        record_transition(job, "running", phase="dispatched")
        append_training_log(job.public_id, f"[SYSTEM] Training workload dispatched ({job.backend}).")
        if hasattr(training_backend(job.backend), "poll"):
            poll_training_job_status.apply_async(args=[str(job.public_id)], countdown=3)
        else:
            append_training_log(job.public_id, "[SYSTEM] Waiting for trusted callback.")
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
        record_training_event(job=job, event_type="completed", message="Training execution completed.")
        record_transition(job, "completed")
    for line in str(result).splitlines()[-500:]:
        append_training_log(job.public_id, line)
    append_training_log(job.public_id, "[SYSTEM] Training completed successfully.")
    return "completed"


@shared_task(bind=True, max_retries=7200)
def poll_training_job_status(self, job_id):
    from apps.observability.services.lifecycle import record_training_event
    from .models import TrainingJob
    from .services.logs import append_training_log

    try:
        job = TrainingJob.objects.select_related("project", "project__owner").get(public_id=job_id)
    except TrainingJob.DoesNotExist:
        return "not_found"

    if job.status in {"completed", "failed", "cancelled"} or job.deletion_requested_at:
        return job.status

    backend = training_backend(job.backend)
    if not hasattr(backend, "poll"):
        return job.status

    result = backend.poll(job)
    current_status = result.get("status")

    if current_status == "running":
        raise self.retry(countdown=5)

    if current_status == "completed":
        logs = result.get("logs", "")
        with transaction.atomic():
            job = TrainingJob.objects.select_for_update().get(pk=job.pk)
            if job.status in {"cancelling", "cancelled"} or job.deletion_requested_at:
                return job.status
            job.mark_finished("completed")
            job.tracking = {**job.tracking, "logs_tail": logs[-6000:]}
            job.save(update_fields=["status", "completed_at", "runtime_seconds", "tracking", "updated_at"])
            job.outputs.update_or_create(
                relative_path="model.tar.gz",
                defaults={"kind": "model", "s3_uri": job.output_uri, "content_type": "application/gzip"},
            )
            record_training_event(job=job, event_type="completed", message="Training execution completed.")
            record_transition(job, "completed")
        for line in logs.splitlines()[-500:]:
            append_training_log(job.public_id, line)
        append_training_log(job.public_id, "[SYSTEM] Training completed successfully.")
        return "completed"

    if current_status == "failed":
        logs = result.get("logs", "")
        error_msg = result.get("error") or f"Training failed with exit code {result.get('exit_code')}"
        with transaction.atomic():
            job = TrainingJob.objects.select_for_update().get(pk=job.pk)
            if job.status in {"cancelling", "cancelled"} or job.deletion_requested_at:
                return job.status
            job.mark_finished("failed")
            job.error_message = error_msg[:12000]
            job.save(update_fields=["status", "completed_at", "runtime_seconds", "error_message", "updated_at"])
            record_training_event(
                job=job, event_type="failed", message="Training execution failed.", metadata={"error": error_msg[:1000]}
            )
            record_transition(job, "failed", reason="Training runtime reported failure")
        for line in logs.splitlines()[-500:]:
            append_training_log(job.public_id, line)
        append_training_log(job.public_id, f"[ERROR] Training failed: {error_msg}")
        return "failed"

    if current_status in {"not_found", "error"}:
        with transaction.atomic():
            job = TrainingJob.objects.select_for_update().get(pk=job.pk)
            if job.status in {"cancelling", "cancelled"} or job.deletion_requested_at:
                return job.status
            job.mark_finished("failed")
            job.error_message = f"Training container error: {result.get('error') or 'Container not found'}"
            job.save(update_fields=["status", "completed_at", "runtime_seconds", "error_message", "updated_at"])
            record_training_event(
                job=job, event_type="failed", message="Training runtime disappeared or errored."
            )
            record_transition(job, "failed", reason="Training runtime disappeared or errored")
        append_training_log(job.public_id, f"[ERROR] {job.error_message}")
        return "failed"

    return job.status


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
            record_transition(job, "cancelling", phase="cancellation_dispatched")
            append_training_log(
                job.public_id,
                "[SYSTEM] Runtime cancellation dispatched; waiting for confirmation.",
            )
            return "cancelling"
    confirm_training_cancellation(job_id)
    return "cancelled"


def confirm_training_cancellation(job_id):
    from apps.observability.services.lifecycle import record_training_event
    from .models import TrainingJob
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
        record_transition(job, "deleted")
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
    from apps.observability.services.lifecycle import record_training_event
    from .models import TrainingJob

    job = TrainingJob.objects.select_related("project", "project__owner").get(public_id=job_id)
    storage = S3Storage()
    tenant_id = job.project.owner.tenant_id
    project_id = job.project.public_id
    storage.delete_prefix(training_output_prefix(tenant_id, project_id, job.public_id))
    storage.delete_prefix(training_mlflow_prefix(tenant_id, project_id, job.public_id))
    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().get(pk=job.pk)
        job.outputs.all().delete()
        record_training_event(
            job=job,
            event_type="outputs_purged",
            message="Training outputs were deleted.",
        )
        record_transition(job, job.status, phase="outputs_purged")
    return "purged"
