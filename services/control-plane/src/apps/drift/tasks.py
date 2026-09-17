import json

from celery import shared_task
from common.logging import record_transition
from django.db import transaction
from django.utils import timezone
from infrastructure.execution import drift_backend
from infrastructure.storage import S3Storage


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
        record_transition(run, "running")
    try:
        result = drift_backend(run.monitor.backend).run(run)
    except Exception as exc:
        DriftRun.objects.filter(pk=run.pk).update(
            status="failed", error_message=str(exc)[:12000], completed_at=timezone.now()
        )
        record_transition(
            run, "failed", reason="Drift backend execution failed", error_type=type(exc).__name__, exc_info=True,
        )
        raise
    if isinstance(result, dict) and result.get("dispatched"):
        record_transition(run, "running", phase="dispatched")
        if hasattr(drift_backend(run.monitor.backend), "poll"):
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
        if run.has_drift:
            transaction.on_commit(lambda: handle_drift_detected.delay(str(run.public_id)))
    return "completed"


@shared_task(bind=True, max_retries=120)
def poll_drift_run_status(self, run_id):
    from .models import DriftRun

    try:
        run = DriftRun.objects.select_related("monitor").get(public_id=run_id)
    except DriftRun.DoesNotExist:
        return "not_found"

    if run.status in {"completed", "failed", "cancelled"}:
        return run.status

    backend = drift_backend(run.monitor.backend)
    if not hasattr(backend, "poll"):
        return run.status

    result = backend.poll(run)
    current_status = result.get("status")

    if current_status == "running":
        raise self.retry(countdown=5)

    if current_status == "completed":
        with transaction.atomic():
            run = DriftRun.objects.select_for_update().get(pk=run.pk)
            if run.status in {"completed", "failed", "cancelled"}:
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
            if run.has_drift:
                transaction.on_commit(lambda: handle_drift_detected.delay(str(run.public_id)))
        return "completed"

    if current_status == "failed":
        error_msg = result.get("error") or f"Drift analysis failed with exit code {result.get('exit_code')}"
        with transaction.atomic():
            run = DriftRun.objects.select_for_update().get(pk=run.pk)
            if run.status in {"completed", "cancelled"}:
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
            if run.status in {"completed", "cancelled"}:
                return run.status
            run.status = "failed"
            run.error_message = f"Drift container error: {result.get('error') or 'Container not found'}"
            run.completed_at = run.completed_at or timezone.now()
            run.save(update_fields=["status", "error_message", "completed_at"])
            record_transition(run, "failed", reason="Drift runtime disappeared or errored")
        return "failed"

    return run.status


@shared_task(bind=True)
def handle_drift_detected(self, run_id):
    """Entry point hook for Continuous Training (CT) and Degradation-Aware Diagnosis.

    Triggered when a DriftRun records has_drift = True.
    Coordinates evidence aggregation and prepares the workload for the
    Multi-Evidence Diagnosis Engine and Retraining Decision Policy.
    """
    import logging

    from .models import DriftRun

    logger = logging.getLogger("apps.drift.tasks")
    try:
        run = DriftRun.objects.select_related(
            "monitor",
            "monitor__version",
            "monitor__version__project",
        ).get(public_id=run_id)
    except DriftRun.DoesNotExist:
        logger.warning(f"handle_drift_detected: DriftRun {run_id} not found.")
        return "not_found"

    version = run.monitor.version
    project = version.project
    drift_score = run.drift_score
    summary = run.summary or {}

    logger.info(
        f"[CONTINUOUS_TRAINING_HOOK] Drift detected for project '{project.name}' "
        f"(version '{version.version}', public_id={version.public_id}). "
        f"Drift Score: {drift_score}. Ready for Degradation-Aware CT Engine."
    )

    evidence_payload = {
        "drift_run_id": str(run.public_id),
        "model_version_id": str(version.public_id),
        "project_id": str(project.public_id),
        "drift_score": drift_score,
        "has_drift": True,
        "summary": summary,
        "triggered_at": timezone.now().isoformat(),
    }

    return {
        "status": "drift_handled",
        "model_version_id": str(version.public_id),
        "drift_score": drift_score,
        "evidence": evidence_payload,
    }
