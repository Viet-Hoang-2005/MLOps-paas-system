import uuid

from django.db import transaction

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor, DriftRun
from apps.drift.tasks import execute_drift_run
from common.api.exceptions import Conflict


def request_run(monitor, idempotency_key=None):
    key = idempotency_key or str(uuid.uuid4())
    with transaction.atomic():
        project = ModelProject.objects.select_for_update().filter(pk=monitor.version.project_id).first()
        if not project or project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        monitor = DriftMonitor.objects.select_related("version").filter(pk=monitor.pk).first()
        if not monitor or monitor.deletion_requested or monitor.version.deletion_requested:
            raise Conflict("This monitor or model version is being deleted.")
        run, created = DriftRun.objects.get_or_create(
            monitor=monitor, idempotency_key=key, defaults={"status": "queued"}
        )
        if created:
            transaction.on_commit(lambda: _enqueue(run))
    return run


def _enqueue(run):
    from apps.observability.services.executions import enqueue_safely

    enqueue_safely(run, execute_drift_run)


def request_cancel(run):
    from django.utils import timezone

    from apps.drift.tasks import cancel_drift_run
    from common.logging import record_transition

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
