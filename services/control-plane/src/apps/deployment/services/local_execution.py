"""Durable local execution watches. Docker/HTTP I/O is outside DB locks."""

import logging
import uuid
from datetime import timedelta

import docker.errors
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.services.logs import append_deployment_log
from common.logging import record_transition, runtime_line
from infrastructure.execution.local_containers import inspect_container, remove_container
from infrastructure.execution.image_references import temporary_image_reference
from infrastructure.runtime_health import RuntimeHealthProbe

logger = logging.getLogger(__name__)
WATCH_FIELDS = ["next_execution_check_at", "execution_check_token", "execution_check_lease_until"]


def dispatch_execution_checks():
    from apps.deployment.execution_tasks import check_local_execution

    count = 0
    now = timezone.now()
    for model, kind in ((Build, "build"), (Deployment, "deploy")):
        with transaction.atomic():
            rows = list(model.objects.filter(backend="docker", next_execution_check_at__lte=now)
                .filter(Q(execution_check_lease_until__isnull=True) | Q(execution_check_lease_until__lte=now))
                .select_for_update(skip_locked=True).order_by("next_execution_check_at", "pk")[:100])
            for row in rows:
                token = uuid.uuid4()
                model.objects.filter(pk=row.pk).update(
                    execution_check_token=token, execution_check_lease_until=now + timedelta(seconds=30),
                )

                def publish(model=model, pk=row.pk, kind=kind, public_id=str(row.public_id), token=token):
                    try:
                        check_local_execution.apply_async(args=[kind, public_id, str(token)], queue="celery", expires=10)
                    except Exception:
                        model.objects.filter(pk=pk, execution_check_token=token).update(
                            execution_check_token=None, execution_check_lease_until=None,
                        )
                        logger.warning("Local execution enqueue failed kind=%s id=%s", kind, public_id)
                        raise

                transaction.on_commit(publish, robust=True)
                count += 1
    return count


def _locked(model, resource, token):
    project_id = resource.project_id if model is Build else resource.version.project_id
    project = ModelProject.objects.select_for_update().filter(pk=project_id).first()
    row = model.objects.select_for_update().filter(pk=resource.pk).first()
    if not project or not row or str(row.execution_check_token) != str(token):
        return None, None
    if not row.execution_check_lease_until or row.execution_check_lease_until <= timezone.now():
        return None, None
    return project, row


def _release(row, *, finished=False):
    row.next_execution_check_at = None if finished else timezone.now() + timedelta(seconds=settings.LOCAL_EXECUTION_POLL_SECONDS)
    row.execution_check_token = None
    row.execution_check_lease_until = None
    row.save(update_fields=WATCH_FIELDS)


def _failure(row, kind, message):
    if kind == "build":
        if row.status != "building":
            return
        row.status = "failed"
        row.completed_at = timezone.now()
        row.execution_completed_at = row.completed_at
        row.error_message = message
        row.save(update_fields=["status", "error_message", "completed_at", "execution_completed_at"])
    else:
        if row.status != "deploying":
            return
        row.status = "failed"
        row.error_message = message
        row.save(update_fields=["status", "error_message"])
        Endpoint.objects.filter(deployment=row).update(health_status="unknown", last_checked_at=None)
        transaction.on_commit(lambda: append_deployment_log(row, message))
    transaction.on_commit(lambda: record_transition(row, "failed", reason=message))


def _cleanup_build(row):
    from apps.deployment.tasks import cleanup_failed_build_artifacts

    if row.status in {"failed", "cancelled"} and row.deletion_state == "active" and not row.version_id:
        row.image_uri = temporary_image_reference(row.project.public_id, row.public_id)
        row.save(update_fields=["image_uri"])

        def publish_cleanup():
            try:
                cleanup_failed_build_artifacts.delay(str(row.public_id), True)
            except Exception:
                # Runtime is already stopped, but the broker did not accept
                # output cleanup. Keep this watch recoverable after commit.
                Build.objects.filter(pk=row.pk, status__in=("failed", "cancelled")).update(
                    next_execution_check_at=timezone.now() + timedelta(seconds=settings.LOCAL_EXECUTION_POLL_SECONDS),
                )
                logger.warning("Build output cleanup enqueue failed id=%s", row.public_id)
                raise

        transaction.on_commit(publish_cleanup, robust=True)


def check_execution(kind, public_id, token, *, inspector=None, remover=None, probe=None):
    if kind not in {"build", "deploy"}:
        return "ignored"
    model = Build if kind == "build" else Deployment
    related = "project__owner" if kind == "build" else "version__project__owner"
    row = model.objects.select_related(related).filter(
        public_id=public_id, backend="docker", execution_check_token=token,
        execution_check_lease_until__gt=timezone.now(),
    ).first()
    if not row:
        return "ignored"
    new_token = uuid.uuid4()
    if not model.objects.filter(pk=row.pk, execution_check_token=token,
        execution_check_lease_until__gt=timezone.now()).update(execution_check_token=new_token):
        return "ignored"
    token = new_token
    inspector = inspector or inspect_container
    remover = remover or remove_container
    project = row.project if kind == "build" else row.version.project
    expired = bool(row.execution_deadline_at and row.execution_deadline_at <= timezone.now())
    inactive = not project.is_active or project.deletion_state != "active" or getattr(row, "deletion_state", "active") != "active"
    logs = ""
    health = "unknown"
    try:
        try:
            container = inspector(row, kind)
            state = container.attrs.get("State", {})
            running = state.get("Status") in {"running", "created", "restarting", "paused"}
            missing = False
        except docker.errors.NotFound:
            container, state, running, missing = None, {}, False, True
        if missing and not getattr(row, "external_build_id" if kind == "build" else "external_deployment_id"):
            # Dispatch may still be preparing presigned URLs or starting Docker.
            if not expired and row.status in {"building", "deploying"}:
                with transaction.atomic():
                    _, current = _locked(model, row, token)
                    if current:
                        _release(current)
                return "starting"
        if kind == "build" and container and not running:
            raw = container.logs(stdout=True, stderr=True, tail=200).decode("utf-8", errors="replace")
            logs = "\n".join(runtime_line(line) for line in raw[-20000:].splitlines())
        terminal = row.status in ({"ready", "failed", "cancelled"} if kind == "build" else {"failed", "stopped"})
        remove = inactive or expired or (terminal and (kind == "deploy" or row.status != "ready"))
        if kind == "deploy" and row.status == "succeeded":
            remove = False
        if remove or (kind == "build" and terminal and not running):
            remover(row, kind)
            remove = True
        elif kind == "deploy" and running and row.status == "deploying":
            endpoint = Endpoint.objects.filter(deployment=row).first()
            health = (probe or RuntimeHealthProbe()).check(
                url=endpoint.internal_url if endpoint else "", flavor=row.version.flavor,
                project_id=project.public_id, version_id=row.version.public_id,
            )
    except Exception as exc:
        # Docker/monitor outages are not fabricated model failures. Retry until
        # we can inspect/stop safely, including after the execution deadline.
        logger.warning("Local execution observation failed kind=%s id=%s type=%s", kind, public_id, type(exc).__name__)
        with transaction.atomic():
            _, current = _locked(model, row, token)
            if current:
                if current.execution_deadline_at and current.execution_deadline_at <= timezone.now():
                    _failure(current, kind, "Execution deadline exceeded; runtime cleanup awaits Docker availability.")
                _release(current)
        return "retry"
    with transaction.atomic():
        current_project, current = _locked(model, row, token)
        if not current:
            return "ignored"
        inactive = not current_project.is_active or current_project.deletion_state != "active" or getattr(current, "deletion_state", "active") != "active"
        expired = bool(current.execution_deadline_at and current.execution_deadline_at <= timezone.now())
        if logs and kind == "build":
            current.logs = logs
            current.save(update_fields=["logs"])
        if inactive or current.status in {"cancelled", "stopped"}:
            if inactive and current.status in {"building", "deploying"}:
                current.status = "cancelled" if kind == "build" else "stopped"
                current.save(update_fields=["status"])
            # A stop/delete racing with I/O is cleaned on the next pass if needed.
            if kind == "build" and remove:
                _cleanup_build(current)
            _release(current, finished=remove)
            return "cancelled"
        if kind == "build":
            if current.status in {"ready", "failed"}:
                done = remove or missing
                if done:
                    _cleanup_build(current)
                _release(current, finished=done)
                return current.status
            message = ""
            if expired:
                message = "Build execution exceeded its deadline."
            elif missing:
                message = "Build container disappeared before a result was confirmed."
            elif not running and state.get("ExitCode", 1) != 0:
                message = "Build container exited with an error. See build logs."
            elif not running:
                if current.callback_wait_until is None:
                    current.callback_wait_until = timezone.now() + timedelta(seconds=settings.LOCAL_BUILD_CALLBACK_GRACE_SECONDS)
                    current.save(update_fields=["callback_wait_until"])
                elif current.callback_wait_until <= timezone.now():
                    message = "Build container exited successfully but no valid result callback was received."
            if message:
                _failure(current, kind, message)
                # Keep a final cleanup pass: the exit grace branch did not remove.
                _release(current)
                return "failed"
        elif current.status == "succeeded":
            _release(current, finished=True)
            return "succeeded"
        elif current.status == "failed":
            _release(current, finished=remove)
            return "failed"
        elif expired or missing or not running:
            _failure(current, kind, "Runtime readiness timed out." if expired else "Runtime container is not running.")
        elif health == "healthy":
            from apps.deployment.tasks import _mark_deployment_succeeded

            _mark_deployment_succeeded(current)
            _release(current, finished=True)
            return "succeeded"
        else:
            transaction.on_commit(lambda: append_deployment_log(current, "Runtime is not ready yet; next check is scheduled."))
        _release(current)
    return "waiting"
