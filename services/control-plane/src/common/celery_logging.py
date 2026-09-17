"""Carry bounded correlation via signals, never task arguments or results."""

import math
import time
import uuid

from celery.signals import before_task_publish, setup_logging, task_failure, task_postrun, task_prerun, task_retry

from common.logging import configure_logging, failure_reported
from common.logging_utils import Summary, bind_context, current_context, get_logger, log_event, reset_context

logger = get_logger(__name__)
task_summary = Summary(logger, "celery_task_summary")
CONTEXT_FIELDS = (
    "request_id",
    "tenant_id",
    "project_id",
    "build_id",
    "deployment_id",
    "training_job_id",
    "drift_run_id",
    "model_version_id",
)


def _resource_context(name, args, kwargs):
    """Only known resource UUID arguments may enter logging context."""
    tasks = {
        "apps.deployment.tasks.execute_build": ("build_id", "build_id"),
        "apps.deployment.tasks.cancel_build": ("build_id", "build_id"),
        "apps.deployment.tasks.cleanup_failed_build_artifacts": ("build_id", "build_id"),
        "apps.deployment.tasks.execute_deployment": ("deployment_id", "deployment_id"),
        "apps.deployment.tasks.check_deployment_health": ("deployment_id", "deployment_id"),
        "apps.deployment.tasks.stop_deployment": ("deployment_id", "deployment_id"),
        **{
            f"apps.training.tasks.{task}": ("job_id", "training_job_id")
            for task in (
                "execute_training_job",
                "poll_training_job_status",
                "cancel_training_job",
                "delete_training_job",
                "purge_training_job_outputs",
            )
        },
        **{
            f"apps.drift.tasks.{task}": ("run_id", "drift_run_id")
            for task in (
                "execute_drift_run",
                "poll_drift_run_status",
                "handle_drift_detected",
            )
        },
        **{
            f"apps.catalog.tasks.{task}": ("project_id", "project_id")
            for task in (
                "execute_project_deletion",
                "complete_project_deletion",
            )
        },
    }
    if name not in tasks:
        return {}
    argument, field = tasks[name]
    value = (kwargs or {}).get(argument, args[0] if args else None)
    try:
        return {field: str(uuid.UUID(str(value)))}
    except (ValueError, TypeError, AttributeError):
        return {}


@setup_logging.connect(dispatch_uid="control_plane.logging.configure")
def setup_celery_logging(**kwargs):
    configure_logging()


def _correlation(values):
    return {
        key: value
        for key, value in values.items()
        if key in CONTEXT_FIELDS
        and isinstance(value, str)
        and len(value) <= 128
        and all(char.isalnum() or char in "._:-" for char in value)
    }


@before_task_publish.connect(dispatch_uid="control_plane.logging.publish")
def publish_context(headers=None, **kwargs):
    if headers is not None:
        headers["mlops_context"] = _correlation(current_context())


@task_prerun.connect(dispatch_uid="control_plane.logging.start")
def task_start(task_id=None, task=None, args=None, kwargs=None, **extra):
    if task is None:
        return
    incoming = (getattr(task.request, "headers", None) or {}).get("mlops_context", {})
    incoming = _correlation(incoming) if isinstance(incoming, dict) else {}
    task.request._logging_token = bind_context(
        **{
            **dict.fromkeys(current_context()),
            **incoming,
            **_resource_context(task.name, args, kwargs),
            "celery_task_id": task_id,
            "operation": task.name,
            "attempt": getattr(task.request, "retries", 0) + 1,
        }
    )
    task.request._logging_started_at = time.monotonic()
    task.request._logging_failure_token = failure_reported.set(False)


@task_failure.connect(dispatch_uid="control_plane.logging.failure")
def task_failed(sender=None, exception=None, traceback=None, **kwargs):
    if failure_reported.get():
        return
    log_event(
        logger,
        "ERROR",
        "celery.task.failed",
        "Celery invocation failed",
        operation=getattr(sender, "name", "unknown"),
        error_type=type(exception).__name__ if exception is not None else "Exception",
        exc_info=(type(exception), exception, traceback) if exception is not None else None,
    )
    failure_reported.set(True)


@task_retry.connect(dispatch_uid="control_plane.logging.retry")
def task_retried(sender=None, request=None, reason=None, **kwargs):
    when = getattr(reason, "when", None)
    countdown = when if type(when) in (int, float) and math.isfinite(when) and when >= 0 else None
    log_event(
        logger,
        "WARNING",
        "celery.task.retry",
        "Celery invocation scheduled for retry",
        operation=getattr(sender, "name", "unknown"),
        attempt=getattr(request, "retries", 0) + 1,
        retry_seconds=countdown,
    )


@task_postrun.connect(dispatch_uid="control_plane.logging.finish")
def task_finish(task_id=None, task=None, state=None, **kwargs):
    if task is None:
        return
    token = getattr(task.request, "_logging_token", None)
    try:
        if state == "FAILURE" and not failure_reported.get():
            task_failed(sender=task)
        started = getattr(task.request, "_logging_started_at", time.monotonic())
        task_summary.record(
            success=state == "SUCCESS",
            duration_ms=(time.monotonic() - started) * 1000,
            tasks=1,
            retries=1 if state == "RETRY" else 0,
        )
    finally:
        if token is not None:
            reset_context(token)
            del task.request._logging_token
        failure_token = getattr(task.request, "_logging_failure_token", None)
        if failure_token is not None:
            failure_reported.reset(failure_token)
            del task.request._logging_failure_token
