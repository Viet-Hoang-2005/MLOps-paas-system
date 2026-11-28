import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.observability.execution.leases import _release, _valid, enqueue_safely
from apps.observability.execution.resources import ARGO_SERVING_KINDS, TERMINAL, model_for, project_for, resource_for
from common.telemetry.logging import record_transition
from infrastructure.storage import S3Storage

logger = logging.getLogger(__name__)


def _finish(row, kind, status, message="", finished_at=None):
    if kind == "training" and status == "completed" and row.tracking.get("output_contract") != 2:
        from apps.training.outputs.finalization import enqueue_output

        enqueue_output(row, finished_at)
        return

    if kind == "training":
        row.mark_finished(status)
        if finished_at:
            row.completed_at = finished_at
            started = row.runtime_started_at or row.started_at or finished_at
            row.runtime_seconds = max(0, int((finished_at - started).total_seconds()))
        row.save(update_fields=["status", "completed_at", "runtime_seconds"])
        from apps.observability.lifecycle import record_training_event

        record_training_event(job=row, event_type=status, message=(message or f"Training {status}.")[:1000])
    else:
        row.status, row.completed_at = status, timezone.now()
        row.save(update_fields=["status", "completed_at"])
    row.error_message = message[:12000]
    row.save(update_fields=["error_message"])
    transaction.on_commit(lambda: record_transition(row, status, reason=message or None))
    transaction.on_commit(lambda row_id=row.pk, exec_kind=kind: _notify_execution_finished(exec_kind, row_id))


def _notify_execution_finished(kind, row_id):
    try:
        if kind == "training":
            from apps.notifications.events import notify_training_result
            from apps.training.jobs.models import TrainingJob

            job = TrainingJob.objects.select_related("workspace", "project", "owner").filter(pk=row_id).first()
            if job:
                notify_training_result(job)
        else:
            from apps.drift.models import DriftRun
            from apps.notifications.events import notify_drift_result

            run = DriftRun.objects.select_related("monitor__version__project__owner").filter(pk=row_id).first()
            if run:
                notify_drift_result(run)
    except Exception:
        logger.exception("Failed to dispatch %s completion notification for id=%s", kind, row_id)


def _store_runtime_metadata(current, kind, observation):
    fields = []
    runtime_id = observation.get("runtime_id")
    if runtime_id:
        field = "external_job_id" if kind == "training" else "external_run_id"
        setattr(current, field, runtime_id)
        fields.append(field)
    started = observation.get("started_at")
    started = parse_datetime(started) if isinstance(started, str) else started
    if started and not current.runtime_started_at and started <= timezone.now():
        current.runtime_started_at = started
        current.started_at = started
        fields.append("started_at")
        runtime = current.max_runtime_seconds if kind == "training" else settings.DRIFT_MAX_RUNTIME_SECONDS
        current.execution_deadline_at = started + timedelta(seconds=runtime)
    finished = observation.get("finished_at")
    finished = parse_datetime(finished) if isinstance(finished, str) else finished
    if kind == "training":
        if observation.get("logs"):
            current.tracking = {**current.tracking, "logs_tail": observation["logs"][-6000:]}
            fields.append("tracking")
        if current.status in TERMINAL and current.runtime_started_at and current.completed_at:
            end = finished or current.completed_at
            current.completed_at = end
            current.runtime_seconds = max(0, int((end - current.runtime_started_at).total_seconds()))
            fields.extend(["completed_at", "runtime_seconds"])
    if fields:
        current.save(update_fields=fields)
    return finished


def _completion_data(row, kind):
    if kind == "training":
        return None
    from botocore.config import Config

    storage = S3Storage(client_config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 0}))
    from infrastructure.storage.paths import drift_run_prefix

    project = project_for(row, kind)
    prefix = f"s3://{storage.bucket}/{drift_run_prefix(project.owner.tenant_id, project.public_id, row.monitor.public_id, row.public_id)}"
    if getattr(row, "summary_uri", "") != prefix + "summary.json":
        raise ValueError("Drift output does not belong to this run.")
    summary = json.loads(storage.read(row.summary_uri))
    if not isinstance(summary, dict):
        raise ValueError("Invalid drift summary.")
    if summary.get("status") == "skipped":
        return summary
    for field, filename in (
        ("report_html_uri", "report.html"),
        ("report_json_uri", "report.json"),
    ):
        if getattr(row, field) != prefix + filename:
            raise ValueError("Drift output does not belong to this run.")
    for uri in (row.report_html_uri, row.report_json_uri):
        bucket, key = storage.parse_uri(uri)
        storage.client.head_object(Bucket=bucket, Key=key)
    return summary


def apply_observation(kind, public_id, token, observation):
    row = resource_for(kind, public_id)
    if not _valid(row, token):
        return "ignored"
    if kind in ARGO_SERVING_KINDS:
        from apps.deployment.execution.argo_recovery import apply_argo_observation

        return apply_argo_observation(row, kind, token, observation)
    observed = observation["status"]
    data = None
    if observed == "completed" and row.status not in TERMINAL and not row.execution_stop_requested:
        try:
            data = _completion_data(row, kind)
            if kind == "drift" and isinstance(data, dict) and data.get("status") == "skipped":
                observed = "skipped"
                observation = {**observation, "status": "skipped"}
        except Exception as exc:
            from botocore.exceptions import ClientError

            missing = isinstance(exc, ValueError) or (
                isinstance(exc, ClientError) and exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}
            )
            if getattr(row, "status", None) == "skipped" or (
                isinstance(getattr(row, "summary", None), dict) and row.summary.get("status") == "skipped"
            ):
                observed = "skipped"
            else:
                observed = "failed" if missing else "error"
            observation = {**observation, "status": observed, "error": "Runtime output verification failed."}
    project = project_for(row, kind)
    with transaction.atomic():
        if kind == "training" and row.backend == "argo":
            from apps.training.resources.quota import lock_owner

            lock_owner(row.owner_id)
        if project:
            project = type(project).objects.select_for_update().get(pk=project.pk)
        current = model_for(kind).objects.select_for_update().get(pk=row.pk)
        if not _valid(current, token):
            return "ignored"
        finished = _store_runtime_metadata(current, kind, observation)
        quota_settled = True
        if kind == "training" and current.backend == "argo":
            from apps.training.resources.quota import update_observation

            quota_settled = update_observation(
                current,
                started_at=current.runtime_started_at,
                finished_at=finished,
                stopped=observed == "stopped",
                never_started=observation.get("never_started", False),
            )
        now = timezone.now()
        dispatch_expired = bool(
            current.dispatch_deadline_at and (current.runtime_started_at or now) > current.dispatch_deadline_at
        )
        runtime_expired = bool(current.execution_deadline_at and now >= current.execution_deadline_at)
        output_finished = (
            parse_datetime(current.tracking.get("output_runtime_finished_at", ""))
            if kind == "training" and current.status == "uploading"
            else None
        )
        end = finished or output_finished
        finished_in_time = bool(
            end
            and current.execution_deadline_at
            and end <= current.execution_deadline_at
            and (observed == "completed" or output_finished)
        )
        if (
            (dispatch_expired or (runtime_expired and not finished_in_time))
            and current.status not in TERMINAL
            and current.status != "cancelling"
        ):
            _finish(current, kind, "failed", "Execution deadline exceeded.")
            current.execution_stop_requested = True
            current.observation_status = "cleanup_pending"
        if observed == "error":
            _release(current, observation.get("error", "Observation unavailable."))
            return current.status
        inactive = (project and project.deletion_state != "active") or bool(
            getattr(current, "deletion_requested_at", None)
        )
        if observed == "stopped":
            if kind == "training" and current.backend == "docker":
                from apps.training.resources.local_capacity import release

                release(current)
            if kind == "drift" and current.monitor.backend == "argo" and not current.argo_stop_confirmed_at:
                current.argo_stop_confirmed_at = timezone.now()
                current.save(update_fields=["argo_stop_confirmed_at"])
            if not quota_settled:
                current.observation_status = "cleanup_pending"
                _release(current, "Training runtime timing is unavailable; quota reconciliation is pending.")
                return current.status
            if current.status not in TERMINAL:
                _finish(current, kind, "cancelled")
            current.observation_status = "ok"
            current.execution_stop_requested = False
            _release(current)
            current.next_execution_check_at = None
            current.save(update_fields=["next_execution_check_at"])
            if kind == "training":
                if project and project.deletion_state == "deleting":
                    from apps.catalog.projects.tasks import execute_project_deletion
                    from apps.observability.execution.argo_stops import project_has_unconfirmed_argo_stops

                    if (
                        not project_has_unconfirmed_argo_stops(project)
                        and not project.training_jobs.exclude(status__in=("completed", "failed", "cancelled")).exists()
                    ):
                        transaction.on_commit(lambda: execute_project_deletion.delay(str(project.public_id)))
                elif current.deletion_requested_at:
                    from apps.training.jobs.tasks import delete_training_job

                    transaction.on_commit(lambda: enqueue_safely(current, delete_training_job))
            return current.status
        if inactive or current.execution_stop_requested or current.status in TERMINAL or current.status == "cancelling":
            current.observation_status = "cleanup_pending"
            current.execution_stop_requested = True
        elif observed in {"dispatched", "running"}:
            was_queued = current.status == "queued"
            if current.status != "uploading":
                current.status = "running"
            current.save(update_fields=["status", "started_at"])
            if kind == "training" and was_queued:
                from apps.observability.lifecycle import record_training_event

                record_training_event(job=current, event_type="started", message="Training workload dispatched.")
        elif kind == "training" and current.status == "uploading" and observed in {"completed", "not_found"}:
            from apps.training.outputs.finalization import enqueue_output

            enqueue_output(current, finished)
        elif (
            observed == "not_found"
            and not current.runtime_started_at
            and (row.backend if kind == "training" else row.monitor.backend) == "argo"
        ):
            current.status = "queued"
            current.save(update_fields=["status"])
        elif observed in {"completed", "failed", "not_found", "skipped"}:
            if data is not None:
                current.summary = data
                current.drift_score = data.get("drift_score", data.get("share_of_drifted_columns"))
                current.has_drift = data.get("has_drift", data.get("dataset_drift"))
                current.save(update_fields=["summary", "drift_score", "has_drift"])
            if observed == "completed":
                status = "completed"
            elif observed == "skipped":
                status = "skipped"
            else:
                status = "failed"
            _finish(
                current,
                kind,
                status,
                observation.get("error", "Runtime is missing." if observed == "not_found" else ""),
                finished_at=finished,
            )
            if current.status != "uploading":
                current.observation_status = "cleanup_pending"
                current.execution_stop_requested = True
        _release(current)
        return current.status
