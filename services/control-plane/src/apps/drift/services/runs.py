import uuid

from django.db import transaction

from apps.drift.models import DriftRun
from apps.drift.tasks import execute_drift_run


def request_run(monitor, idempotency_key=None):
    from common.api.exceptions import Conflict

    if monitor.version.project.deletion_state != "active":
        raise Conflict("This project is being deleted.")
    key = idempotency_key or str(uuid.uuid4())
    run, created = DriftRun.objects.get_or_create(monitor=monitor, idempotency_key=key, defaults={"status": "queued"})
    if created:
        transaction.on_commit(lambda: _enqueue(run))
    return run


def _enqueue(run):
    from apps.observability.services.executions import enqueue_safely
    enqueue_safely(run, execute_drift_run)


def request_cancel(run):
    from django.utils import timezone
    from common.logging import record_transition
    from apps.drift.tasks import cancel_drift_run

    with transaction.atomic():
        run = DriftRun.objects.select_for_update().get(pk=run.pk)
        if run.status in {"completed", "failed", "cancelled", "skipped"}:
            return run
        run.status = "cancelled"
        run.completed_at = run.completed_at or timezone.now()
        run.save(update_fields=["status", "completed_at"])
        record_transition(run, "cancelled")
        transaction.on_commit(lambda: cancel_drift_run.delay(str(run.public_id)))
    return run

