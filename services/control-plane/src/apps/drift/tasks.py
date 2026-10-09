import json

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from common.logging import record_transition
from infrastructure.execution import drift_backend, polls_runtime_status
from infrastructure.storage import S3Storage

# "skipped" is final: the run ended without a result because of too few samples.
TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled", "skipped"})


@shared_task(
    bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_jitter=True, max_retries=5,
    soft_time_limit=50, time_limit=55,
)
def execute_drift_run(self, run_id):
    from django.conf import settings
    if settings.EXECUTION_WATCH_ENABLED:
        from apps.observability.services.executions import reconcile
        return reconcile("drift", run_id)
    from .models import DriftRun

    with transaction.atomic():
        run = (
            DriftRun.objects.select_for_update()
            .select_related(
                "monitor",
                "monitor__version",
                "monitor__version__project",
                "monitor__version__project__owner",
                "monitor__reference_asset",
            )
            .get(public_id=run_id)
        )
        if run.status in {"completed", "cancelled", "failed"} or run.monitor.version.project.deletion_state != "active":
            return run.status
        run.status = "running"
        run.started_at = run.started_at or timezone.now()
        run.celery_task_id = self.request.id or run.celery_task_id
        run.save(update_fields=["status", "started_at", "celery_task_id"])
        record_transition(run, "running")
    try:
        result = drift_backend(run.monitor.backend).run(run)
    except Exception as exc:
        DriftRun.objects.filter(pk=run.pk).update(
            status="failed", error_message=str(exc)[:12000], completed_at=timezone.now()
        )
        record_transition(
            run,
            "failed",
            reason="Drift backend execution failed",
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise
    if isinstance(result, dict) and result.get("dispatched"):
        record_transition(run, "running", phase="dispatched")
        if polls_runtime_status(drift_backend(run.monitor.backend)):
            poll_drift_run_status.apply_async(args=[str(run.public_id)], countdown=5)
        return "running"

    with transaction.atomic():
        run = DriftRun.objects.select_for_update().get(pk=run.pk)
        if run.status == "cancelled":
            return "cancelled"

        if not run.summary and run.summary_uri:
            try:
                storage = S3Storage()
                bucket, key = storage.parse_uri(run.summary_uri)
                obj = storage.client.get_object(Bucket=bucket, Key=key)
                summary = json.loads(obj["Body"].read().decode("utf-8"))
                run.summary = summary
                run.drift_score = summary.get("drift_score", summary.get("share_of_drifted_columns"))
                run.has_drift = summary.get("has_drift", summary.get("dataset_drift"))
            except Exception:
                pass

        already_completed = run.status == "completed"
        run.status = "completed"
        run.completed_at = run.completed_at or timezone.now()
        run.error_message = ""
        run.save(update_fields=["status", "completed_at", "error_message", "summary", "drift_score", "has_drift"])
        if not already_completed:
            record_transition(run, "completed")
    return "completed"


@shared_task(bind=True, max_retries=120, soft_time_limit=50, time_limit=55)
def poll_drift_run_status(self, run_id):
    from django.conf import settings
    if settings.EXECUTION_WATCH_ENABLED:
        from apps.observability.services.executions import reconcile
        return reconcile("drift", run_id)
    from .models import DriftRun

    try:
        run = DriftRun.objects.select_related("monitor").get(public_id=run_id)
    except DriftRun.DoesNotExist:
        return "not_found"

    if run.status in TERMINAL_RUN_STATUSES:
        return run.status

    backend = drift_backend(run.monitor.backend)
    if not polls_runtime_status(backend):
        return run.status

    result = backend.poll(run)
    current_status = result.get("status")

    if current_status == "running":
        raise self.retry(countdown=5)

    if current_status == "completed":
        with transaction.atomic():
            run = DriftRun.objects.select_for_update().get(pk=run.pk)
            if run.status in TERMINAL_RUN_STATUSES:
                return run.status
            if not run.summary and run.summary_uri:
                try:
                    storage = S3Storage()
                    bucket, key = storage.parse_uri(run.summary_uri)
                    obj = storage.client.get_object(Bucket=bucket, Key=key)
                    summary = json.loads(obj["Body"].read().decode("utf-8"))
                    run.summary = summary
                    run.drift_score = summary.get("drift_score", summary.get("share_of_drifted_columns"))
                    run.has_drift = summary.get("has_drift", summary.get("dataset_drift"))
                except Exception:
                    pass
            run.status = "completed"
            run.completed_at = run.completed_at or timezone.now()
            run.error_message = ""
            run.save(update_fields=["status", "completed_at", "error_message", "summary", "drift_score", "has_drift"])
            record_transition(run, "completed")
        return "completed"

    if current_status == "failed":
        error_msg = result.get("error") or f"Drift analysis failed with exit code {result.get('exit_code')}"
        with transaction.atomic():
            run = DriftRun.objects.select_for_update().get(pk=run.pk)
            if run.status in {"completed", "cancelled", "skipped"}:
                return run.status
            run.status = "failed"
            run.error_message = error_msg[:12000]
            run.completed_at = run.completed_at or timezone.now()
            run.save(update_fields=["status", "error_message", "completed_at"])
            record_transition(run, "failed", reason="Drift runtime reported failure")
        return "failed"

    if current_status in {"not_found", "error"}:
        with transaction.atomic():
            run = DriftRun.objects.select_for_update().get(pk=run.pk)
            if run.status in {"completed", "cancelled", "skipped"}:
                return run.status
            run.status = "failed"
            run.error_message = f"Drift container error: {result.get('error') or 'Container not found'}"
            run.completed_at = run.completed_at or timezone.now()
            run.save(update_fields=["status", "error_message", "completed_at"])
            record_transition(run, "failed", reason="Drift runtime disappeared or errored")
        return "failed"

    return run.status
