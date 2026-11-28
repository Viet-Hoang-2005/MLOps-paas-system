import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.deployment.execution.logs import append_deployment_log, reset_deployment_logs
from apps.deployment.models import Deployment, Endpoint
from apps.deployment.serving.model_server_cache import invalidate_model_server_cache
from common.telemetry.logging import record_transition
from infrastructure.execution import deployment_backend

logger = logging.getLogger(__name__)


STOP_CLAIMABLE = {"pending", "deploying", "succeeded", "unconfirmed"}


def claim_deployment_stop(project, deployment):
    """Claim the stop under the caller's project and deployment locks.

    The stopped status is written before the runtime is touched, so a late
    readiness result can no longer promote this deployment.
    """
    if deployment.status in STOP_CLAIMABLE:
        deployment.status = "stopped"
        deployment.save(update_fields=["status", "updated_at"])
    Endpoint.objects.filter(deployment=deployment).update(
        health_status="unknown", last_checked_at=None, health_check_token=None, health_check_lease_until=None
    )
    if project.active_deployment_id == deployment.pk:
        project.active_deployment = None
        project.save(update_fields=["active_deployment", "updated_at"])
    version_id = str(deployment.version.public_id)
    public_id = str(deployment.public_id)
    transaction.on_commit(lambda: invalidate_model_server_cache(version_id))
    transaction.on_commit(lambda: stop_deployment.delay(public_id))


def _mark_deployment_succeeded(deployment):
    from apps.catalog.models import ModelProject
    from apps.drift.models import DriftMonitor

    with transaction.atomic():
        project = ModelProject.objects.select_for_update().get(pk=deployment.version.project_id)
        deployment = Deployment.objects.select_for_update(of=("self",)).get(pk=deployment.pk)
        if (
            not project.is_active
            or project.deletion_state != "active"
            or deployment.status not in {"deploying", "unconfirmed"}
        ):
            return False
        old_id = project.active_deployment_id
        Deployment.objects.filter(pk=deployment.pk).update(
            status="succeeded", deployed_at=timezone.now(), error_message=""
        )
        Endpoint.objects.filter(deployment=deployment).update(health_status="healthy", last_checked_at=timezone.now())
        project.active_deployment = deployment
        project.save(update_fields=["active_deployment", "updated_at"])
        DriftMonitor.objects.filter(version__project=project).exclude(version_id=deployment.version_id).update(
            is_active=False
        )
        if old_id and old_id != deployment.pk:
            old = Deployment.objects.select_for_update(of=("self",)).select_related("version").get(pk=old_id)
            claim_deployment_stop(project, old)
        version_id = str(deployment.version.public_id)
        transaction.on_commit(lambda: invalidate_model_server_cache(version_id))
        transaction.on_commit(
            lambda: append_deployment_log(deployment, "Runtime passed readiness checks; deployment succeeded.")
        )
    record_transition(deployment, "succeeded")
    return True


def mark_argo_deployment_failed(deployment, message):
    deployment.status = "failed"
    deployment.error_message = message
    deployment.save(update_fields=["status", "error_message", "updated_at"])
    Endpoint.objects.filter(deployment=deployment).update(health_status="unhealthy", last_checked_at=timezone.now())
    version_id = str(deployment.version.public_id)
    transaction.on_commit(lambda: invalidate_model_server_cache(version_id))
    transaction.on_commit(lambda: append_deployment_log(deployment, message))
    record_transition(deployment, "failed", reason="Deployment workflow failed")


@shared_task(
    name="apps.deployment.tasks.execute_deployment",
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def execute_deployment(self, deployment_id):
    from apps.catalog.models import ModelProject

    candidate = Deployment.objects.select_related("version").get(public_id=deployment_id)
    with transaction.atomic():
        ModelProject.objects.select_for_update().get(pk=candidate.version.project_id)
        deployment = (
            Deployment.objects.select_for_update(of=("self",))
            .select_related("version", "version__project", "version__project__owner", "build")
            .get(public_id=deployment_id)
        )
        if deployment.status in {"succeeded", "failed", "stopped", "unconfirmed"}:
            return deployment.status
        if deployment.version.project.deletion_state != "active" or deployment.version.deletion_requested:
            deployment.status = "stopped"
            deployment.stopped_at = timezone.now()
            deployment.error_message = "Project or version deletion is in progress."
            deployment.save(update_fields=["status", "stopped_at", "error_message", "updated_at"])
            return "stopped"
        starting = deployment.status == "pending"
        deployment.status = "deploying"
        deployment.celery_task_id = self.request.id or deployment.celery_task_id
        deployment.error_message = ""
        deployment.save(update_fields=["status", "celery_task_id", "error_message", "updated_at"])
        if deployment.backend == "docker":
            Deployment.objects.filter(pk=deployment.pk).update(
                execution_deadline_at=deployment.execution_deadline_at
                or timezone.now() + timedelta(seconds=settings.LOCAL_DEPLOY_READINESS_TIMEOUT_SECONDS),
                next_execution_check_at=timezone.now(),
            )
        elif deployment.backend == "argo":
            Deployment.objects.filter(pk=deployment.pk).update(
                execution_deadline_at=deployment.execution_deadline_at or timezone.now() + timedelta(minutes=33),
                next_execution_check_at=timezone.now(),
            )
        record_transition(deployment, "deploying")
    if starting:
        reset_deployment_logs(deployment, "Starting deployment process.")
    append_deployment_log(deployment, f"Dispatching {deployment.backend} deployment backend.")
    try:
        backend = deployment_backend(deployment.backend)
        backend.log_sink = lambda message: append_deployment_log(deployment, message)
        endpoint = backend.deploy(deployment)
    except Exception as exc:
        if isinstance(exc, (ConnectionError, TimeoutError)) and self.request.retries < self.max_retries:
            raise
        invalidate_model_server_cache(str(deployment.version.public_id))
        changed = Deployment.objects.filter(pk=deployment.pk, status="deploying").update(
            status="failed", error_message=str(exc)[:12000]
        )
        if not changed:
            deployment.refresh_from_db()
            return deployment.status
        record_transition(
            deployment,
            "failed",
            reason="Deployment backend execution failed",
            error_type=type(exc).__name__,
            exc_info=True,
        )
        append_deployment_log(deployment, f"Deployment failed: {exc}")
        raise
    deployment.version.project.refresh_from_db(fields=["deletion_state"])
    if deployment.version.project.deletion_state != "active":
        backend.stop(deployment)
        invalidate_model_server_cache(str(deployment.version.public_id))
        Deployment.objects.filter(pk=deployment.pk).update(status="stopped", stopped_at=timezone.now())
        Endpoint = type(endpoint)
        Endpoint.objects.filter(pk=endpoint.pk).update(
            health_status="unknown",
            last_checked_at=None,
            health_check_token=None,
            health_check_lease_until=None,
        )
        return "stopped"
    deployment.refresh_from_db()
    if deployment.status in {"succeeded", "failed", "stopped", "unconfirmed"}:
        if deployment.status == "stopped":
            backend.stop(deployment)
        return deployment.status
    append_deployment_log(deployment, "Runtime resource dispatched; waiting for readiness confirmation.")
    record_transition(deployment, "deploying", phase="dispatched")
    if deployment.backend == "argo":
        mark_deployment_unconfirmed.apply_async(args=[str(deployment.public_id)], countdown=33 * 60)
    return "deploying"


@shared_task(name="apps.deployment.tasks.mark_deployment_unconfirmed")
def mark_deployment_unconfirmed(deployment_id):
    from apps.catalog.models import ModelProject

    candidate = Deployment.objects.select_related("version").get(public_id=deployment_id)
    with transaction.atomic():
        ModelProject.objects.select_for_update().get(pk=candidate.version.project_id)
        deployment = (
            Deployment.objects.select_for_update(of=("self",)).select_related("version").get(public_id=deployment_id)
        )
        if deployment.status != "deploying" or deployment.backend != "argo":
            return deployment.status
        deployment.status = "unconfirmed"
        deployment.error_message = "No deployment result callback arrived before the deadline. Check the workflow logs."
        deployment.save(update_fields=["status", "error_message", "updated_at"])
        version_id = str(deployment.version.public_id)
        error_message = deployment.error_message
        transaction.on_commit(lambda: invalidate_model_server_cache(version_id))
        transaction.on_commit(lambda: append_deployment_log(deployment, error_message))
        record_transition(deployment, "unconfirmed", reason="Deployment result callback timed out")
    return "unconfirmed"


@shared_task(
    name="apps.deployment.tasks.stop_deployment",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
    reject_on_worker_lost=True,
)
def stop_deployment(self, deployment_id):
    from apps.catalog.models import ModelProject

    deployment = Deployment.objects.select_related("version", "build").get(public_id=deployment_id)
    with transaction.atomic():
        # Stops queued before the claim existed still win over a late promotion.
        project = ModelProject.objects.select_for_update().get(pk=deployment.version.project_id)
        locked = Deployment.objects.select_for_update(of=("self",)).select_related("version").get(pk=deployment.pk)
        if locked.status in STOP_CLAIMABLE:
            locked.status = "stopped"
            locked.save(update_fields=["status", "updated_at"])
        if project.active_deployment_id == locked.pk:
            project.active_deployment = None
            project.save(update_fields=["active_deployment", "updated_at"])
    result = deployment_backend(deployment.backend).stop(deployment)
    if deployment.backend == "argo" and (not isinstance(result, dict) or not result.get("confirmed")):
        return "stopping"
    Deployment.objects.filter(pk=deployment.pk, stopped_at__isnull=True).update(stopped_at=timezone.now())
    Endpoint.objects.filter(deployment=deployment).update(
        health_status="unknown", last_checked_at=None, health_check_token=None, health_check_lease_until=None
    )
    invalidate_model_server_cache(str(deployment.version.public_id))
    if locked.status != "stopped":
        # A failed deployment whose workflow still created a runtime: the runtime is removed
        # but the recorded outcome stays what it was.
        append_deployment_log(deployment, f"Removed the runtime of a {locked.status} deployment.")
        return locked.status
    append_deployment_log(deployment, "Deployment stopped.")
    record_transition(deployment, "stopped")
    return "stopped"


@shared_task(
    name="apps.deployment.tasks.reconcile_stopped_deployments",
    ignore_result=True,
    expires=60,
    soft_time_limit=50,
    time_limit=55,
)
def reconcile_stopped_deployments():
    """Re-dispatch stops whose runtime removal never completed.

    A stop is claimed in the database first and the runtime is removed by a queued
    task. If that task is lost (worker or broker down between commit and enqueue) or
    exhausts its retries, nothing else would ever remove the runtime. ``stopped_at``
    is written only after ``backend.stop`` succeeds, so a stopped deployment without
    it past the grace period still owns a runtime. ``stop_deployment`` is idempotent.
    """
    cutoff = timezone.now() - timedelta(seconds=settings.STOP_RECONCILE_GRACE_SECONDS)
    stale = Deployment.objects.filter(status="stopped", updated_at__lt=cutoff).filter(
        Q(backend="docker", stopped_at__isnull=True) | Q(backend="argo", argo_stop_confirmed_at__isnull=True)
    )
    dispatched = 0
    for public_id in stale.order_by("updated_at").values_list("public_id", flat=True)[
        : settings.STOP_RECONCILE_BATCH_SIZE
    ]:
        # A failing stop is retried at most once per grace period, not on every scan.
        if cache.add(f"deployment-stop-reconcile:{public_id}", 1, timeout=settings.STOP_RECONCILE_GRACE_SECONDS):
            stop_deployment.delay(str(public_id))
            dispatched += 1
    if dispatched:
        logger.warning("Re-dispatched %s stale deployment stop(s).", dispatched)
    return dispatched
