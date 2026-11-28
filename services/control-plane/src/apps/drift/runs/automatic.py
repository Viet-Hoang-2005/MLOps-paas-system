"""Durable, internal automatic-drift triggering from production data signals."""

from django.db import transaction

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor, DriftRun
from apps.drift.runs.lifecycle import request_run
from apps.production.models import PredictionRecord


def production_data_count_for_version(model_version_id: str) -> int:
    """Count eligible monitoring samples from the Consumer-owned CT dataset."""
    return PredictionRecord.objects.filter(model_version__public_id=model_version_id).count()


def request_automatic_drift_runs(model_version_id: str) -> int:
    """Create at most one new run per active monitor and threshold crossing.

    The project row is locked so concurrent outbox deliveries cannot independently
    observe the same crossing.  The persisted watermark and deterministic run
    idempotency key make replay after worker failures safe.
    """
    with transaction.atomic():
        project_id = (
            ModelProject.objects.filter(versions__public_id=model_version_id).values_list("pk", flat=True).first()
        )
        if not ModelProject.objects.select_for_update().filter(pk=project_id, deletion_state="active").first():
            return 0
        monitors = list(
            DriftMonitor.objects.filter(
                version__public_id=model_version_id,
                version__deletion_requested=False,
                deletion_requested=False,
                is_active=True,
                version__project__active_deployment__version__public_id=model_version_id,
            ).order_by("pk")
        )
        if not monitors:
            return 0

        current_count = production_data_count_for_version(model_version_id)
        triggered = 0
        for monitor in monitors:
            threshold = monitor.trigger_threshold
            if threshold <= 0 or current_count - monitor.last_automatic_trigger_count < threshold:
                continue

            run_key = f"automatic-drift:{monitor.public_id}:{monitor.last_automatic_trigger_count}:{current_count}"
            existed = DriftRun.objects.filter(monitor=monitor, idempotency_key=run_key).exists()
            request_run(monitor, run_key)
            monitor.last_automatic_trigger_count = current_count
            monitor.save(update_fields=["last_automatic_trigger_count", "updated_at"])
            if not existed:
                triggered += 1
        return triggered
