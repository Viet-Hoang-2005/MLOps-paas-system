"""Durable, internal automatic-drift triggering from production data signals."""

from django.db import transaction

from apps.drift.models import DriftMonitor
from apps.drift.services.runs import request_run
from apps.production.models import PredictionRecord


def production_data_count_for_version(model_version_id: str) -> int:
    """Count eligible monitoring samples from the Consumer-owned CT dataset."""
    return PredictionRecord.objects.filter(model_version__public_id=model_version_id).count()


def request_automatic_drift_runs(model_version_id: str) -> int:
    """Create at most one new run per active monitor and threshold crossing.

    Monitor rows are locked so concurrent outbox deliveries cannot independently
    observe the same crossing.  The persisted watermark and deterministic run
    idempotency key make replay after worker failures safe.
    """
    with transaction.atomic():
        monitors = list(
            DriftMonitor.objects.select_for_update()
            .filter(version__public_id=model_version_id, is_active=True)
            .order_by("pk")
        )
        if not monitors:
            return 0

        current_count = production_data_count_for_version(model_version_id)
        triggered = 0
        for monitor in monitors:
            threshold = monitor.trigger_threshold
            if threshold <= 0 or current_count - monitor.last_automatic_trigger_count < threshold:
                continue

            threshold_bucket = current_count // threshold
            request_run(monitor, f"automatic-drift:{monitor.public_id}:{threshold_bucket}")
            monitor.last_automatic_trigger_count = current_count
            monitor.save(update_fields=["last_automatic_trigger_count", "updated_at"])
            triggered += 1
        return triggered
