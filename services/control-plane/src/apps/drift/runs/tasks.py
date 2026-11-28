from celery import shared_task

from infrastructure.execution import drift_backend


@shared_task(
    name="apps.drift.tasks.execute_drift_run",
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    soft_time_limit=50,
    time_limit=55,
)
def execute_drift_run(self, run_id):
    from apps.observability.execution.reconciliation import reconcile

    return reconcile("drift", run_id)


@shared_task(name="apps.drift.tasks.cancel_drift_run", bind=True, soft_time_limit=30, time_limit=35)
def cancel_drift_run(self, run_id):

    from apps.drift.models import DriftRun

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
