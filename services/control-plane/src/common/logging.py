import contextvars
import logging
import sys
from functools import partial

from django.db import transaction

from common.logging_utils import configure, current_context, get_logger, log_event, sanitize

failure_reported = contextvars.ContextVar("control_plane_failure_reported", default=False)


class FrameworkLogFilter(logging.Filter):
    """Signals/middleware own these records; Celery trace messages contain args."""

    def filter(self, record):
        if record.name == "celery.app.trace":
            return False
        request = getattr(record, "request", None)
        if record.name == "django.request" and getattr(request, "_mlops_request_logging", False):
            return False
        return True


def configure_logging(_config=None):
    configure("control-plane")
    for handler in logging.getLogger().handlers:
        handler.addFilter(FrameworkLogFilter())


def _lifecycle_message(event):
    resource, _, transition = event.partition(".")
    resource_name = resource.replace("_", " ").capitalize()
    phrases = {
        "building": "started",
        "deploying": "started",
        "running": "started",
        "ready": "completed successfully",
        "completed": "completed successfully",
        "healthy": "is healthy",
        "unhealthy": "is unhealthy",
        "failed": "failed",
        "cancelled": "was cancelled",
        "cancelling": "cancellation started",
        "dispatched": "dispatched; waiting for completion",
        "cancellation_dispatched": "cancellation dispatched",
        "deletion_dispatched": "deletion dispatched",
        "completion_enqueued": "completion queued",
        "deleted": "was deleted",
        "outputs_purged": "outputs were purged",
    }
    fallback = f"changed to {transition or 'a new state'}"
    return f"{resource_name} {phrases.get(transition, fallback)}"


def _emit_lifecycle(level, event, payload):
    log_event(get_logger("control_plane.lifecycle"), level, event, _lifecycle_message(event), **payload)
    if level == "ERROR":
        failure_reported.set(True)


def lifecycle_event(event, *, resource_type, resource_id, status, source="task", **fields):
    """Snapshot correlation now, emit only when the mutation commits."""
    if fields.get("exc_info") is True:
        fields["exc_info"] = sys.exc_info()
    payload = {
        **current_context(),
        **fields,
        "resource_id": str(resource_id),
        f"{resource_type}_id": str(resource_id),
        "status": status,
        "source": source,
    }
    transaction.on_commit(
        partial(
            _emit_lifecycle,
            "ERROR" if status in {"failed", "delete_failed", "unhealthy"} else "INFO",
            event,
            payload,
        )
    )


def runtime_line(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return sanitize(str(value), limit=2048)


def record_transition(resource, status, *, phase=None, source="task", reason=None, error_type=None, exc_info=None):
    resource_type = {
        "Build": "build",
        "Deployment": "deployment",
        "TrainingJob": "training_job",
        "DriftRun": "drift_run",
        "ModelProject": "project",
    }[type(resource).__name__]
    # Only use relations already loaded by orchestration; logging must not issue queries.
    related = resource
    correlation = {}
    for relation in ("monitor", "version", "project", "owner"):
        related = related._state.fields_cache.get(relation) or related
        if type(related).__name__ == "ModelVersion":
            correlation["model_version_id"] = str(related.public_id)
        elif type(related).__name__ == "ModelProject":
            correlation["project_id"] = str(related.public_id)
        if relation == "owner" and getattr(related, "tenant_id", None):
            correlation["tenant_id"] = str(related.tenant_id)
    lifecycle_event(
        f"{resource_type}.{phase or status}",
        resource_type=resource_type,
        resource_id=resource.public_id,
        status=status,
        source=source,
        reason=reason,
        error_type=error_type,
        exc_info=exc_info,
        **correlation,
    )
