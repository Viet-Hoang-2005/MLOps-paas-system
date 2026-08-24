import uuid

from django.db import transaction

from apps.drift.models import DriftRun
from apps.drift.tasks import execute_drift_run


def request_run(monitor, idempotency_key=None):
    key = idempotency_key or str(uuid.uuid4())
    run, created = DriftRun.objects.get_or_create(monitor=monitor, idempotency_key=key, defaults={"status": "queued"})
    if created:
        transaction.on_commit(lambda: _enqueue(run))
    return run


def _enqueue(run):
    result = execute_drift_run.delay(str(run.public_id))
    DriftRun.objects.filter(pk=run.pk).update(celery_task_id=result.id)
