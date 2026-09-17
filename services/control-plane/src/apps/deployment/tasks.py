import logging

from celery import shared_task
from common.logging import failure_reported, record_transition
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from infrastructure.execution import build_backend, deployment_backend
from infrastructure.execution.image_cleanup import BuildImageCleaner
from infrastructure.execution.image_references import temporary_image_reference
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_prefix

from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.services.cache import invalidate_model_server_cache
from apps.deployment.services.logs import append_deployment_log, reset_deployment_logs
from apps.observability.services.outbox import enqueue_event
from apps.registry.services.versions import register_successful_build

logger = logging.getLogger(__name__)


def _mark_deployment_healthy(deployment):
    Deployment = type(deployment)
    Deployment.objects.filter(pk=deployment.pk).update(
        status="healthy", deployed_at=timezone.now(), error_message=""
    )
    Endpoint.objects.filter(deployment=deployment).update(
        health_status="healthy", last_checked_at=timezone.now()
    )
    invalidate_model_server_cache(str(deployment.version.public_id))
    append_deployment_log(deployment, "Endpoint passed health checks; deployment is healthy.")
    record_transition(deployment, "healthy")
    enqueue_event(
        topic="deployment.events",
        aggregate_type="deployment",
        aggregate_id=deployment.public_id,
        event_type="deployment.changed",
        payload={"deployment_id": str(deployment.public_id), "status": "healthy"},
    )


@shared_task(bind=True)
def execute_build(self, build_id):
    with transaction.atomic():
        build = (
            Build.objects.select_for_update()
            .select_related("project", "project__owner")
            .get(public_id=build_id)
        )
        if build.status in {"ready", "cancelled"}:
            return build.status
        if build.project.deletion_state != "active":
            build.status = "cancelled"
            build.completed_at = timezone.now()
            build.error_message = "Project deletion is in progress."
            build.save(update_fields=["status", "completed_at", "error_message", "updated_at"])
            return "cancelled"
        build.status = "building"
        build.started_at = build.started_at or timezone.now()
        build.celery_task_id = self.request.id or build.celery_task_id
        build.error_message = ""
        build.save(update_fields=["status", "started_at", "celery_task_id", "error_message", "updated_at"])
        record_transition(build, "building")
    try:
        result = build_backend(build.backend).run(build)
    except Exception as exc:
        already_failed = Build.objects.filter(pk=build.pk, status="failed").exists()
        Build.objects.filter(pk=build.pk).update(
            status="failed", error_message=str(exc)[:12000], completed_at=timezone.now()
        )
        if not already_failed:
            record_transition(
                build, "failed", reason="Build backend execution failed", error_type=type(exc).__name__, exc_info=True,
            )
        else:
            # A trusted callback already recorded this failure while the backend ran.
            failure_reported.set(True)
        cleanup_failed_build_artifacts.delay(str(build.public_id), False)
        raise
    if isinstance(result, dict) and result.get("dispatched"):
        record_transition(build, "building", phase="dispatched")
        return "building"
    build.refresh_from_db()
    registered_locally = build.status != "ready"
    if build.status != "ready":
        image_uri = build.image_uri or temporary_image_reference(
            build.project.public_id,
            build.public_id,
            registry=settings.HARBOR_REGISTRY_URL if build.backend == "argo" else "",
            registry_project=settings.HARBOR_USER_PROJECT,
        )
        build = register_successful_build(build=build, image_uri=image_uri, image_digest=build.image_digest)
    Build.objects.filter(pk=build.pk).update(logs=str(result)[-20000:], completed_at=timezone.now())
    if registered_locally:
        record_transition(build, "ready")
    return "ready"


@shared_task(bind=True)
def cancel_build(self, build_id):
    build = Build.objects.select_related("project").get(public_id=build_id)
    build_backend(build.backend).cancel(build)
    Build.objects.filter(pk=build.pk).update(status="cancelled", completed_at=timezone.now())
    record_transition(build, "cancelled")
    cleanup_failed_build_artifacts.delay(str(build.public_id), bool(build.image_uri))
    return "cancelled"


@shared_task(
    bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5
)
def cleanup_failed_build_artifacts(self, build_id, delete_image=False):
    build = Build.objects.select_related("project", "project__owner").prefetch_related("input_assets").get(
        public_id=build_id
    )
    if build.status == "ready":
        return "retained"
    if delete_image and build.image_uri:
        BuildImageCleaner().delete(build)
    storage = S3Storage()
    storage.delete_prefix(build_prefix(build.project.owner.tenant_id, build.project.public_id, build.public_id))
    build.input_assets.update(s3_uri="", purged_at=timezone.now())
    return "purged"


@shared_task(
    bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_jitter=True, max_retries=5
)
def execute_deployment(self, deployment_id):
    with transaction.atomic():
        deployment = (
            Deployment.objects.select_for_update()
            .select_related("version", "version__project", "version__project__owner", "build")
            .get(public_id=deployment_id)
        )
        if deployment.status in {"healthy", "stopped"}:
            return deployment.status
        if deployment.version.project.deletion_state != "active":
            deployment.status = "stopped"
            deployment.stopped_at = timezone.now()
            deployment.error_message = "Project deletion is in progress."
            deployment.save(update_fields=["status", "stopped_at", "error_message", "updated_at"])
            return "stopped"
        starting = deployment.status == "pending"
        deployment.status = "deploying"
        deployment.celery_task_id = self.request.id or deployment.celery_task_id
        deployment.error_message = ""
        deployment.save(update_fields=["status", "celery_task_id", "error_message", "updated_at"])
        record_transition(deployment, "deploying")
    if starting:
        reset_deployment_logs(deployment, "Starting deployment process.")
    append_deployment_log(deployment, f"Dispatching {deployment.backend} deployment backend.")
    try:
        backend = deployment_backend(deployment.backend)
        backend.log_sink = lambda message: append_deployment_log(deployment, message)
        endpoint = backend.deploy(deployment)
    except Exception as exc:
        invalidate_model_server_cache(str(deployment.version.public_id))
        Deployment.objects.filter(pk=deployment.pk).update(status="failed", error_message=str(exc)[:12000])
        record_transition(
            deployment, "failed", reason="Deployment backend execution failed", error_type=type(exc).__name__,
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
        Endpoint.objects.filter(pk=endpoint.pk).update(health_status="stopped")
        return "stopped"
    append_deployment_log(deployment, "Runtime resource created; waiting for endpoint health check.")
    record_transition(deployment, "deploying", phase="dispatched")
    if endpoint.health_status == "healthy":
        _mark_deployment_healthy(deployment)
        return "healthy"
    check_deployment_health.apply_async(args=[str(deployment.public_id)], countdown=10)
    return "deploying"


@shared_task(bind=True, max_retries=30)
def check_deployment_health(self, deployment_id):
    deployment = Deployment.objects.select_related("version", "build").get(public_id=deployment_id)
    if deployment.status in {"healthy", "failed", "stopped"}:
        return deployment.status
    healthy, metadata = deployment_backend(deployment.backend).health(deployment)
    Endpoint.objects.filter(deployment=deployment).update(
        health_status="healthy" if healthy else "unknown",
        last_checked_at=timezone.now(),
        metadata=metadata,
    )
    if healthy:
        _mark_deployment_healthy(deployment)
        return "healthy"
    if self.request.retries >= self.max_retries:
        invalidate_model_server_cache(str(deployment.version.public_id))
        Deployment.objects.filter(pk=deployment.pk).update(
            status="unhealthy", error_message="Endpoint health check timed out."
        )
        append_deployment_log(deployment, "Endpoint health check timed out.")
        record_transition(deployment, "unhealthy", reason="Endpoint health check timed out")
        return "unhealthy"
    append_deployment_log(deployment, "Endpoint is not healthy yet; retrying health check.")
    raise self.retry(countdown=min(10 + self.request.retries * 2, 60))


@shared_task(bind=True)
def stop_deployment(self, deployment_id):
    deployment = Deployment.objects.select_related("version", "build").get(public_id=deployment_id)
    deployment_backend(deployment.backend).stop(deployment)
    Deployment.objects.filter(pk=deployment.pk).update(status="stopped", stopped_at=timezone.now())
    invalidate_model_server_cache(str(deployment.version.public_id))
    append_deployment_log(deployment, "Deployment stopped.")
    record_transition(deployment, "stopped")
    enqueue_event(
        topic="deployment.events",
        aggregate_type="deployment",
        aggregate_id=deployment.public_id,
        event_type="deployment.changed",
        payload={"deployment_id": str(deployment.public_id), "status": "stopped"},
    )
    return "stopped"
