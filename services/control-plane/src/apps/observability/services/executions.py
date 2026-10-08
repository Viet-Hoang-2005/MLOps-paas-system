"""PostgreSQL-backed execution reconciliation, independent of Celery delivery."""

import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Case, CharField, Q, Value, When
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.drift.models import DriftRun
from apps.training.models import TrainingJob
from common.logging import record_transition
from infrastructure.execution import drift_backend, training_backend
from infrastructure.storage import S3Storage

logger = logging.getLogger(__name__)
TERMINAL = {"completed", "failed", "cancelled"}
ACTIVE = {"queued", "running", "uploading", "cancelling"}
WATCH_FIELDS = [field.name for field in TrainingJob._meta.fields if field.name in {
    "next_execution_check_at", "execution_check_token", "execution_check_lease_until",
    "dispatch_deadline_at", "execution_deadline_at", "runtime_started_at",
    "execution_stop_requested", "observation_status", "observation_error", "observation_failures",
}]


def _enqueue_observation_status():
    return Case(When(observation_status="cleanup_pending", then=Value("cleanup_pending")),
        default=Value("retrying"), output_field=CharField())


def model_for(kind):
    if kind not in {"training", "drift"}:
        raise ValueError("Unsupported execution kind")
    return TrainingJob if kind == "training" else DriftRun


def resource_for(kind, public_id):
    related = ("project__owner",) if kind == "training" else ("monitor__version__project__owner", "monitor__reference_asset")
    return model_for(kind).objects.select_related(*related).filter(public_id=public_id).first()


def project_for(row, kind):
    return row.project if kind == "training" else row.monitor.version.project


def backend_for(row, kind):
    return training_backend(row.backend) if kind == "training" else drift_backend(row.monitor.backend)


def ensure_watch(row):
    from django.db.models.functions import Coalesce
    from django.db.models import Value
    now = timezone.now()
    type(row).objects.filter(pk=row.pk).update(next_execution_check_at=now,
        dispatch_deadline_at=Coalesce("dispatch_deadline_at", Value(now + timedelta(seconds=settings.EXECUTION_DISPATCH_TIMEOUT_SECONDS))))


def enqueue_safely(row, task):
    ensure_watch(row)
    try:
        result = task.delay(str(row.public_id))
        type(row).objects.filter(pk=row.pk).update(celery_task_id=result.id)
    except Exception as exc:
        type(row).objects.filter(pk=row.pk).update(observation_status=_enqueue_observation_status(), observation_error=f"Enqueue unavailable: {type(exc).__name__}")
        logger.warning("Execution dispatch deferred kind=%s id=%s", row._meta.model_name, row.public_id)


def claim(kind, public_id=None):
    now = timezone.now()
    with transaction.atomic():
        candidates = Q(status__in=ACTIVE) | Q(observation_status="cleanup_pending")
        if kind == "training":
            candidates |= Q(deletion_requested_at__isnull=False)
        rows = model_for(kind).objects.select_for_update(skip_locked=True).filter(
            candidates
        ).filter(Q(execution_check_lease_until__isnull=True) | Q(execution_check_lease_until__lte=now))
        if public_id:
            rows = rows.filter(public_id=public_id)
        else:
            rows = rows.filter(Q(next_execution_check_at__isnull=True) | Q(next_execution_check_at__lte=now))
        claimed = []
        lease_seconds = getattr(settings, "EXECUTION_CHECK_LEASE_SECONDS", 300)
        for row in rows.order_by("pk")[:100]:
            row.execution_check_token = uuid.uuid4()
            row.execution_check_lease_until = now + timedelta(seconds=lease_seconds)
            row.dispatch_deadline_at = row.dispatch_deadline_at or now + timedelta(seconds=settings.EXECUTION_DISPATCH_TIMEOUT_SECONDS)
            row.save(update_fields=WATCH_FIELDS)
            claimed.append((str(row.public_id), str(row.execution_check_token)))
        return claimed


def scan():
    from apps.observability.tasks import reconcile_job_execution

    if not settings.EXECUTION_WATCH_ENABLED:
        return 0
    count = 0
    lease_seconds = getattr(settings, "EXECUTION_CHECK_LEASE_SECONDS", 300)
    for kind in ("training", "drift"):
        for public_id, token in claim(kind):
            try:
                reconcile_job_execution.apply_async(args=[kind, public_id, token], expires=min(60, lease_seconds))
                count += 1
            except Exception:
                model_for(kind).objects.filter(public_id=public_id, execution_check_token=token).update(
                    execution_check_lease_until=None, observation_status=_enqueue_observation_status(), observation_error="Broker unavailable.",
                )
    return count


def _valid(row, token):
    return bool(row and str(row.execution_check_token) == str(token) and row.execution_check_lease_until and row.execution_check_lease_until > timezone.now())


def _release(row, error=""):
    row.observation_failures = row.observation_failures + 1 if error else 0
    row.observation_error = error[:1000]
    if row.observation_status != "cleanup_pending":
        row.observation_status = "retrying" if error else "ok"
    delay = min(60, 5 * 2 ** min(max(row.observation_failures - 1, 0), 4)) if error else 15
    row.next_execution_check_at = timezone.now() + timedelta(seconds=delay)
    row.execution_check_token = None
    row.execution_check_lease_until = None
    row.save(update_fields=WATCH_FIELDS)


def signed_observation_token(kind, row, token):
    project = project_for(row, kind)
    return signing.dumps({"kind": kind, "id": str(row.public_id), "lease": str(token),
        "tenant": str(project.owner.tenant_id), "project": str(project.public_id)}, salt="execution-observation")


def reconcile(kind, public_id, token=None):
    if token is None:
        claimed = claim(kind, public_id)
        if not claimed:
            row = resource_for(kind, public_id)
            return row.status if row else "not_found"
        _, token = claimed[0]
    row = resource_for(kind, public_id)
    if not _valid(row, token):
        return "ignored"
    try:
        backend = backend_for(row, kind)
    except Exception as exc:
        return apply_observation(kind, public_id, token, {"status": "error", "error": type(exc).__name__})
    now = timezone.now()
    project = project_for(row, kind)
    stopping = (row.execution_stop_requested or row.status == "cancelling" or row.status in TERMINAL
        or project.deletion_state != "active" or bool(getattr(row, "deletion_requested_at", None)))
    if stopping:
        with transaction.atomic():
            current = model_for(kind).objects.select_for_update().get(pk=row.pk)
            if not _valid(current, token):
                return "ignored"
            current.execution_stop_requested = True
            current.observation_status = "cleanup_pending"
            current.save(update_fields=WATCH_FIELDS)
        row.refresh_from_db()
        try:
            if getattr(backend, "setting_name", ""):
                backend.reconcile(row, kind, token, stop=True)
                return "awaiting_observation"
            snapshot = backend.poll(row)
            with transaction.atomic():
                current = model_for(kind).objects.select_for_update().get(pk=row.pk)
                if not _valid(current, token):
                    return "ignored"
                _store_runtime_metadata(current, kind, snapshot)
                current.save(update_fields=WATCH_FIELDS)
            backend.cleanup(row)
            return apply_observation(kind, public_id, token, {"status": "stopped"})
        except Exception as exc:
            return apply_observation(kind, public_id, token, {"status": "error", "error": type(exc).__name__})
    try:
        if getattr(backend, "setting_name", "") and row.status == "running":
            backend.reconcile(row, kind, token)
            return "awaiting_observation"
        result = backend.poll(row)
        if (result["status"] == "created" or (result["status"] == "not_found" and row.status == "queued")) and row.dispatch_deadline_at > now:
            if kind == "training":
                from apps.training.services.resources import validate_resources
                validate_resources({}, row)
            backend.run(row)
            return apply_observation(kind, public_id, token, {"status": "dispatched"})
        return apply_observation(kind, public_id, token, result)
    except Exception as exc:
        from rest_framework.exceptions import ValidationError
        import docker.errors
        if kind == "training" and row.accelerator_type == "gpu" and isinstance(exc, docker.errors.APIError) and any(word in str(exc).lower() for word in ("gpu", "device driver", "nvidia")):
            return apply_observation(kind, public_id, token, {"status": "failed", "error": "Requested GPU is unavailable on this Docker host."})
        if isinstance(exc, ValidationError):
            return apply_observation(kind, public_id, token, {"status": "failed", "error": str(exc.detail)})
        return apply_observation(kind, public_id, token, {"status": "error", "error": type(exc).__name__})


def _finish(row, kind, status, message="", finished_at=None):
    if kind == "training":
        row.mark_finished(status)
        if finished_at:
            row.completed_at = finished_at
            started = row.runtime_started_at or row.started_at or row.created_at
            row.runtime_seconds = max(0, int((finished_at - started).total_seconds()))
        row.save(update_fields=["status", "completed_at", "runtime_seconds"])
        if status == "completed":
            row.outputs.update_or_create(relative_path="model.tar.gz", defaults={"kind": "model", "s3_uri": row.output_uri, "content_type": "application/gzip"})
        from apps.observability.services.lifecycle import record_training_event
        record_training_event(job=row, event_type=status, message=(message or f"Training {status}.")[:1000])
    else:
        row.status, row.completed_at = status, timezone.now()
        row.save(update_fields=["status", "completed_at"])
    row.error_message = message[:12000]
    row.save(update_fields=["error_message"])
    transaction.on_commit(lambda: record_transition(row, status, reason=message or None))


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
            current.runtime_seconds = max(0, int((end - current.runtime_started_at).total_seconds()))
            fields.append("runtime_seconds")
    if fields:
        current.save(update_fields=fields)
    return finished


def _completion_data(row, kind):
    if kind == "training":
        from apps.training.services.outputs import verify_training_output
        verify_training_output(row)
        return None
    from botocore.config import Config
    storage = S3Storage(client_config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 0}))
    from infrastructure.storage.paths import drift_run_prefix

    project = project_for(row, kind)
    prefix = f"s3://{storage.bucket}/{drift_run_prefix(project.owner.tenant_id, project.public_id, row.monitor.public_id, row.public_id)}"
    for field, filename in (("summary_uri", "summary.json"), ("report_html_uri", "report.html"), ("report_json_uri", "report.json")):
        if getattr(row, field) != prefix + filename:
            raise ValueError("Drift output does not belong to this run.")
    summary = json.loads(storage.read(row.summary_uri))
    if not isinstance(summary, dict):
        raise ValueError("Invalid drift summary.")
    for uri in (row.report_html_uri, row.report_json_uri):
        bucket, key = storage.parse_uri(uri)
        storage.client.head_object(Bucket=bucket, Key=key)
    return summary


def apply_observation(kind, public_id, token, observation):
    row = resource_for(kind, public_id)
    if not _valid(row, token):
        return "ignored"
    observed = observation["status"]
    data = None
    if observed == "completed" and row.status not in TERMINAL and not row.execution_stop_requested:
        try:
            data = _completion_data(row, kind)
        except Exception as exc:
            from botocore.exceptions import ClientError
            missing = isinstance(exc, ValueError) or (isinstance(exc, ClientError) and exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"})
            observed = "failed" if missing else "error"
            observation = {**observation, "status": observed, "error": "Runtime output verification failed."}
    project = project_for(row, kind)
    with transaction.atomic():
        project = type(project).objects.select_for_update().get(pk=project.pk)
        current = model_for(kind).objects.select_for_update().get(pk=row.pk)
        if not _valid(current, token):
            return "ignored"
        finished = _store_runtime_metadata(current, kind, observation)
        now = timezone.now()
        dispatch_expired = bool(current.dispatch_deadline_at and (current.runtime_started_at or now) > current.dispatch_deadline_at)
        runtime_expired = bool(current.execution_deadline_at and now >= current.execution_deadline_at)
        finished_in_time = bool(observed == "completed" and finished and current.execution_deadline_at and finished <= current.execution_deadline_at)
        if (dispatch_expired or (runtime_expired and not finished_in_time)) and current.status not in TERMINAL and current.status != "cancelling":
            _finish(current, kind, "failed", "Execution deadline exceeded.")
            current.execution_stop_requested = True
            current.observation_status = "cleanup_pending"
        if observed == "error":
            _release(current, observation.get("error", "Observation unavailable."))
            return current.status
        inactive = project.deletion_state != "active" or bool(getattr(current, "deletion_requested_at", None))
        if observed == "stopped":
            if current.status not in TERMINAL:
                _finish(current, kind, "cancelled")
            current.observation_status = "ok"
            current.execution_stop_requested = False
            _release(current)
            current.next_execution_check_at = None
            current.save(update_fields=["next_execution_check_at"])
            if kind == "training" and current.deletion_requested_at:
                from apps.training.tasks import delete_training_job
                transaction.on_commit(lambda: enqueue_safely(current, delete_training_job))
            return current.status
        if inactive or current.execution_stop_requested or current.status in TERMINAL or current.status == "cancelling":
            current.observation_status = "cleanup_pending"
            current.execution_stop_requested = True
        elif observed in {"dispatched", "running"}:
            was_queued = current.status == "queued"
            current.status = "running"
            current.save(update_fields=["status", "started_at"])
            if kind == "training" and was_queued:
                from apps.observability.services.lifecycle import record_training_event
                record_training_event(job=current, event_type="started", message="Training workload dispatched.")
        elif observed == "not_found" and not current.runtime_started_at and (row.backend if kind == "training" else row.monitor.backend) == "argo":
            current.status = "queued"
            current.save(update_fields=["status"])
        elif observed in {"completed", "failed", "not_found"}:
            if data is not None:
                current.summary = data
                current.drift_score = data.get("drift_score", data.get("share_of_drifted_columns"))
                current.has_drift = data.get("has_drift", data.get("dataset_drift"))
                current.save(update_fields=["summary", "drift_score", "has_drift"])
            status = "completed" if observed == "completed" else "failed"
            _finish(current, kind, status, observation.get("error", "Runtime is missing." if observed == "not_found" else ""), finished_at=finished)
            current.observation_status = "cleanup_pending"
            current.execution_stop_requested = True
            if kind == "drift" and current.has_drift and status == "completed":
                from apps.drift.tasks import handle_drift_detected
                transaction.on_commit(lambda: handle_drift_detected.delay(str(current.public_id)), robust=True)
        _release(current)
        return current.status


def execution_metrics():
    now = timezone.now()
    metrics = []
    for kind in ("training", "drift"):
        rows = model_for(kind).objects.all()
        counts = {
            "dispatch_waiting": rows.filter(status__in=ACTIVE, runtime_started_at__isnull=True).count(),
            "lease_expired": rows.filter(execution_check_lease_until__lte=now).count(),
            "observation_error": rows.exclude(observation_error="").count(),
            "deadline_exceeded": rows.filter(error_message="Execution deadline exceeded.").count(),
            "cleanup_pending": rows.filter(observation_status="cleanup_pending").count(),
        }
        for state, count in counts.items():
            metrics.append(f'control_plane_execution_jobs{{kind="{kind}",state="{state}"}} {count}')
    return ("# TYPE control_plane_execution_jobs gauge\n" + "\n".join(metrics) + "\n").encode()
