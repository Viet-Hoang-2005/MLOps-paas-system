import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.deployment.models import Build, Deployment
from apps.observability.execution.leases import ACTIVE, _enqueue_observation_status, _valid, claim
from apps.observability.execution.observations import _store_runtime_metadata, apply_observation
from apps.observability.execution.resources import (
    ARGO_SERVING_KINDS,
    TERMINAL,
    WATCH_FIELDS,
    model_for,
    project_for,
    resource_for,
)
from infrastructure.execution import build_backend, deployment_backend, drift_backend, training_backend

logger = logging.getLogger(__name__)


def backend_for(row, kind):
    if kind == "build":
        return build_backend(row.backend)
    if kind == "deployment":
        return deployment_backend(row.backend)
    return training_backend(row.backend) if kind == "training" else drift_backend(row.monitor.backend)


def _reconcile_argo_deadlines():
    from apps.deployment.execution.argo_recovery import fail_unconfirmed_build
    from apps.deployment.serving.rollout_tasks import mark_deployment_unconfirmed

    now = timezone.now()
    for deployment_id in Deployment.objects.filter(
        backend="argo", status="deploying", execution_deadline_at__lte=now
    ).values_list("public_id", flat=True)[:50]:
        try:
            mark_deployment_unconfirmed(str(deployment_id))
        except Exception:
            logger.warning("Failed to mark expired Argo deployment %s unconfirmed", deployment_id, exc_info=True)

    expired = Build.objects.filter(backend="argo", status="building", execution_deadline_at__lte=now)
    if settings.ARGO_RECONCILE_WEBHOOK_URL:
        expired.filter(callback_wait_until__isnull=True).update(
            callback_wait_until=now + timedelta(seconds=2 * settings.EXECUTION_CHECK_LEASE_SECONDS),
            next_execution_check_at=now,
        )
        return
    for build_id in expired.values_list("public_id", flat=True)[:50]:
        with transaction.atomic():
            build = Build.objects.select_for_update().filter(public_id=build_id, status="building").first()
            if not build or not build.execution_deadline_at or build.execution_deadline_at > now:
                continue
            fail_unconfirmed_build(build, "Build execution exceeded its deadline.")


def scan():
    from apps.observability.execution.tasks import reconcile_job_execution

    count = 0
    lease_seconds = getattr(settings, "EXECUTION_CHECK_LEASE_SECONDS", 300)
    for kind in ("training", "drift", "build", "deployment"):
        if kind in ARGO_SERVING_KINDS and not settings.ARGO_RECONCILE_WEBHOOK_URL:
            continue
        if kind == "training" and not settings.TRAINING_EXECUTION_WATCH_ENABLED:
            continue
        if kind == "drift" and not settings.DRIFT_EXECUTION_WATCH_ENABLED:
            continue
        for public_id, token in claim(kind):
            try:
                reconcile_job_execution.apply_async(args=[kind, public_id, token], expires=min(60, lease_seconds))
                count += 1
            except Exception:
                updates = {"execution_check_lease_until": None}
                if kind not in ARGO_SERVING_KINDS:
                    updates.update(
                        observation_status=_enqueue_observation_status(), observation_error="Broker unavailable."
                    )
                model_for(kind).objects.filter(public_id=public_id, execution_check_token=token).update(**updates)
    return count


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
    if kind in ARGO_SERVING_KINDS:
        if kind == "build" and row.callback_wait_until:
            from apps.deployment.execution.argo_recovery import apply_argo_observation

            # At the deadline the durable result can be recovered even if Argo Events is unavailable.
            deadline_elapsed = row.callback_wait_until <= timezone.now()
            status = apply_argo_observation(
                row,
                kind,
                token,
                {"status": "not_found"},
                retain_lease=not deadline_elapsed,
                deadline_check=deadline_elapsed,
            )
            if status is not None:
                return status
        try:
            backend_for(row, kind).reconcile(row, kind, token)
            return "awaiting_observation"
        except Exception as exc:
            return apply_observation(kind, public_id, token, {"status": "error", "error": type(exc).__name__})
    try:
        backend = backend_for(row, kind)
    except Exception as exc:
        return apply_observation(kind, public_id, token, {"status": "error", "error": type(exc).__name__})
    now = timezone.now()
    project = project_for(row, kind)
    stopping = (
        row.execution_stop_requested
        or row.status == "cancelling"
        or row.status in TERMINAL
        or (project and project.deletion_state != "active")
        or bool(getattr(row, "deletion_requested_at", None))
    )
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
        if (
            result["status"] == "created" or (result["status"] == "not_found" and row.status == "queued")
        ) and row.dispatch_deadline_at > now:
            if kind == "training":
                from apps.training.resources.options import validate_resources

                validate_resources({}, row)
                from apps.training.resources.quota import require_reservation

                require_reservation(row)
            if kind == "training" and row.backend == "docker":
                from apps.training.resources.local_capacity import dispatch_guard

                with dispatch_guard(row, backend.docker.client):
                    backend.run(row)
            else:
                backend.run(row)
            return apply_observation(kind, public_id, token, {"status": "dispatched"})
        return apply_observation(kind, public_id, token, result)
    except Exception as exc:
        import docker.errors
        from rest_framework.exceptions import ValidationError

        from common.api.exceptions import ServiceUnavailable

        if (
            kind == "training"
            and row.accelerator_type == "gpu"
            and isinstance(exc, docker.errors.APIError)
            and any(word in str(exc).lower() for word in ("gpu", "device driver", "nvidia"))
        ):
            return apply_observation(
                kind,
                public_id,
                token,
                {"status": "failed", "error": "Requested GPU is unavailable on this Docker host."},
            )
        if isinstance(exc, ValidationError):
            return apply_observation(kind, public_id, token, {"status": "failed", "error": str(exc.detail)})
        if isinstance(exc, ServiceUnavailable):
            return apply_observation(kind, public_id, token, {"status": "error", "error": str(exc.detail)})
        return apply_observation(kind, public_id, token, {"status": "error", "error": type(exc).__name__})


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
