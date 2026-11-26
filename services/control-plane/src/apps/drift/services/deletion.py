import logging

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ModelProject, WorkspaceAsset
from apps.drift.models import DriftMonitor, DriftRun
from apps.registry.models import ModelArtifact
from common.api.exceptions import Conflict, ServiceUnavailable
from common.redis_client import redis_client
from infrastructure.execution import drift_backend
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import drift_run_prefix, project_prefix

logger = logging.getLogger(__name__)


def delete_drift_run(run: DriftRun, *, storage=None) -> None:
    run = (
        DriftRun.objects.select_related(
            "monitor",
            "monitor__version",
            "monitor__version__project",
            "monitor__version__project__owner",
        )
        .filter(pk=run.pk)
        .first()
    )
    if run is None:
        return

    if run.monitor.backend == "argo":
        DriftRun.objects.filter(pk=run.pk).update(execution_stop_requested=True)
        if run.execution_check_lease_until and run.execution_check_lease_until > timezone.now():
            raise ServiceUnavailable("An Evidently execution check is in progress. Retry deletion.")
    _cleanup_drift_run(run, storage=storage or S3Storage())
    run.delete()


def _cleanup_drift_run(run: DriftRun, *, storage: S3Storage) -> None:
    if run.monitor.backend == "argo" or run.status in {"pending", "queued", "running"}:
        try:
            result = drift_backend(run.monitor.backend).cancel(run)
        except Exception as exc:
            logger.warning("Failed to cancel active drift run %s before deletion", run.public_id, exc_info=True)
            raise ServiceUnavailable("Could not stop the Evidently run. Retry deletion.") from exc
        if (run.monitor.backend == "argo" or isinstance(result, dict)) and (
            not isinstance(result, dict) or not result.get("confirmed")
        ):
            raise ServiceUnavailable("The Evidently run has not stopped. Retry deletion.")

    project = run.monitor.version.project
    prefix = drift_run_prefix(project.owner.tenant_id, project.public_id, run.monitor.public_id, run.public_id)
    try:
        storage.delete_prefix(prefix)
        for uri in (
            run.report_html_uri,
            run.report_json_uri,
            run.summary_uri,
            run.current_data_uri,
            run.report_manifest_uri,
        ):
            if uri and uri.startswith(f"s3://{storage.bucket}/"):
                storage.delete(uri)
    except Exception as exc:
        logger.warning("Failed to delete storage for Evidently run %s", run.public_id, exc_info=True)
        raise ServiceUnavailable("Could not delete the Evidently run files. Retry deletion.") from exc

    try:
        redis_client().delete(f"drift_logs:{run.public_id}")
    except Exception:
        logger.warning("Failed to delete Redis logs for drift run %s", run.public_id, exc_info=True)


def delete_drift_monitor(monitor: DriftMonitor, *, storage=None) -> None:
    with transaction.atomic():
        project = ModelProject.objects.select_for_update().filter(pk=monitor.version.project_id).first()
        monitor = DriftMonitor.objects.select_related("version__project__owner").filter(pk=monitor.pk).first()
        if monitor is None:
            return
        if not project or project.deletion_state != "active" or monitor.version.deletion_requested:
            raise Conflict("This project or model version is being deleted.")
        monitor.deletion_requested = True
        monitor.save(update_fields=["deletion_requested"])
        monitor.runs.update(execution_stop_requested=True)

    cleanup_drift_monitor(monitor, storage=storage or S3Storage())
    monitor.delete()


def cleanup_drift_monitor(monitor: DriftMonitor, *, storage: S3Storage) -> None:
    """Clean external resources so the caller can delete rows after all cleanup succeeds."""
    if monitor.runs.filter(execution_check_lease_until__gt=timezone.now()).exists():
        raise ServiceUnavailable("An Evidently execution check is in progress. Retry deletion.")
    for run in monitor.runs.all():
        _cleanup_drift_run(run, storage=storage)

    project = monitor.version.project
    ref_uri = monitor.reference_uri
    in_bucket = ref_uri and ref_uri.startswith(f"s3://{storage.bucket}/")
    shared = False
    if in_bucket:
        shared = (
            ModelArtifact.objects.filter(uri=ref_uri).exists()
            or WorkspaceAsset.objects.filter(s3_uri=ref_uri).exists()
            or DriftMonitor.objects.exclude(pk=monitor.pk).filter(reference_uri=ref_uri).exists()
        )
    try:
        prefix = f"{project_prefix(project.owner.tenant_id, project.public_id)}/drift/{monitor.public_id}/"
        storage.delete_prefix(prefix)
        if in_bucket and not shared:
            storage.delete(ref_uri)
    except Exception as exc:
        logger.warning("Failed to delete storage for monitor %s", monitor.public_id, exc_info=True)
        raise ServiceUnavailable("Could not delete the monitoring files. Retry deletion.") from exc
