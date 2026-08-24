from celery import shared_task
from django.db import transaction
from django.utils import timezone
from infrastructure.execution import drift_backend


@shared_task(
    bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_jitter=True, max_retries=5
)
def execute_drift_run(self, run_id):
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
        if run.status in {"completed", "cancelled"}:
            return run.status
        run.status = "running"
        run.started_at = run.started_at or timezone.now()
        run.celery_task_id = self.request.id or run.celery_task_id
        run.save(update_fields=["status", "started_at", "celery_task_id"])
    try:
        result = drift_backend(run.monitor.backend).run(run)
    except Exception as exc:
        DriftRun.objects.filter(pk=run.pk).update(
            status="failed", error_message=str(exc)[:12000], completed_at=timezone.now()
        )
        raise
    if isinstance(result, dict) and result.get("dispatched"):
        return "running"
    DriftRun.objects.filter(pk=run.pk).update(
        status="completed",
        completed_at=timezone.now(),
        error_message="",
    )
    return "completed"
