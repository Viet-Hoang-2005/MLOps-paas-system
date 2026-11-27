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
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    soft_time_limit=50,
    time_limit=55,
)
def execute_drift_run(self, run_id):
    from apps.observability.services.executions import reconcile

    return reconcile("drift", run_id)


@shared_task(bind=True, soft_time_limit=30, time_limit=35)
def cancel_drift_run(self, run_id):
    from infrastructure.execution import drift_backend

    from .models import DriftRun

    run = DriftRun.objects.select_related("monitor").filter(public_id=run_id).first()
    if not run:
        return "deleted"
    try:
        result = drift_backend(run.monitor.backend).cancel(run)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=15) from exc
    if run.monitor.backend == "argo" and not result.get("confirmed"):
        raise self.retry(countdown=30, max_retries=10)
    return "cancelled"


@shared_task(ignore_result=True)
def cleanup_drift_monitor_task(monitor_id):
    from apps.drift.models import DriftMonitor
    from apps.drift.services.deletion import delete_drift_monitor

    monitor = DriftMonitor.objects.filter(public_id=monitor_id, deletion_requested=True).first()
    if monitor is None:
        return "missing"
    delete_drift_monitor(monitor)
    return "deleted"
