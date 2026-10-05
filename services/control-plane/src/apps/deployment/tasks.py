import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.health_tasks import probe_runtime_health, scan_runtime_health  # noqa: F401
from apps.deployment.services.cache import invalidate_model_server_cache
from apps.deployment.services.completion import complete_build
from apps.deployment.services.logs import append_deployment_log, reset_deployment_logs
from apps.observability.services.outbox import enqueue_event
from apps.registry.services.versions import register_successful_build
from common.logging import failure_reported, record_transition
from infrastructure.execution import build_backend, deployment_backend
from infrastructure.execution.build_cleanup import stop_build_for_deletion
from infrastructure.execution.image_cleanup import BuildImageCleaner
from infrastructure.execution.image_references import temporary_image_reference
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_prefix

logger = logging.getLogger(__name__)


def _mark_deployment_succeeded(deployment):
    from apps.catalog.models import ModelProject
    from apps.drift.models import DriftMonitor

    with transaction.atomic():
        project = ModelProject.objects.select_for_update().get(pk=deployment.version.project_id)
        deployment = Deployment.objects.select_for_update(of=("self",)).get(pk=deployment.pk)
        if not project.is_active or project.deletion_state != "active" or deployment.status not in {"deploying", "unconfirmed"}:
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
            old = Deployment.objects.select_related("version").get(pk=old_id)
            transaction.on_commit(lambda: invalidate_model_server_cache(str(old.version.public_id)))
            transaction.on_commit(lambda: stop_deployment.delay(str(old.public_id)))
    invalidate_model_server_cache(str(deployment.version.public_id))
    append_deployment_log(deployment, "Runtime passed readiness checks; deployment succeeded.")
    record_transition(deployment, "succeeded")
    enqueue_event(
        topic="deployment.events",
        aggregate_type="deployment",
        aggregate_id=deployment.public_id,
        event_type="deployment.changed",
        payload={"deployment_id": str(deployment.public_id), "status": "succeeded"},
    )
    return True


@shared_task(bind=True)
def execute_build(self, build_id):
    candidate = Build.objects.filter(public_id=build_id).first()
    if not candidate:
        return "not_found"
    with transaction.atomic():
        from apps.catalog.models import ModelProject

        ModelProject.objects.select_for_update().get(pk=candidate.project_id)
        build = Build.objects.select_for_update().select_related("project", "project__owner").get(public_id=build_id)
        if build.deletion_state != "active":
            return "deleting"
        if build.status in {"ready", "cancelled", "failed"}:
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
        if not Build.objects.filter(pk=build.pk, deletion_state="active").exists():
            Build.objects.filter(pk=build.pk).update(status="cancelled", completed_at=timezone.now())
            return "cancelled"
        already_failed = Build.objects.filter(pk=build.pk, status="failed").exists()
        Build.objects.filter(pk=build.pk).exclude(status__in=("cancelled", "ready")).update(
            status="failed", error_message=str(exc)[:12000], completed_at=timezone.now()
        )
        if not already_failed:
            record_transition(
                build,
                "failed",
                reason="Build backend execution failed",
                error_type=type(exc).__name__,
                exc_info=True,
            )
        else:
            # A trusted callback already recorded this failure while the backend ran.
            failure_reported.set(True)
        cleanup_failed_build_artifacts.delay(str(build.public_id), False)
        raise
    if isinstance(result, dict) and result.get("dispatched"):
        record_transition(build, "building", phase="dispatched")
        return "building"
    if not Build.objects.filter(pk=build.pk).exists():
        return "deleted"
    build.refresh_from_db()
    completed_locally = build.status != "ready"
    if build.status not in {"ready", "cancelled", "failed"}:
        image_uri = build.image_uri or temporary_image_reference(
            build.project.public_id,
            build.public_id,
            registry=settings.HARBOR_REGISTRY_URL if build.backend == "argo" else "",
            registry_project=settings.HARBOR_USER_PROJECT,
        )
        build = complete_build(build, image_uri=image_uri, image_digest=build.image_digest)
    Build.objects.filter(pk=build.pk).update(logs=str(result)[-20000:], completed_at=timezone.now())
    if completed_locally:
        record_transition(build, build.status)
    return build.status


@shared_task
def register_build(build_id):
    build = Build.objects.select_related("project").filter(public_id=build_id).first()
    if not build:
        return "not_found"
    if build.version_id:
        return "registered"
    try:
        register_successful_build(build=build, image_uri=build.image_uri, image_digest=build.image_digest)
    except Exception as exc:
        Build.objects.filter(pk=build.pk, version__isnull=True).update(
            registration_status="failed", registration_error=str(exc)[:12000]
        )
        raise
    return "registered"


@shared_task(bind=True)
def cancel_build(self, build_id):
    build = Build.objects.select_related("project").filter(public_id=build_id).first()
    if not build or build.deletion_state != "active":
        return "deleting"
    build_backend(build.backend).cancel(build)
    Build.objects.filter(pk=build.pk).update(status="cancelled", completed_at=timezone.now())
    record_transition(build, "cancelled")
    cleanup_failed_build_artifacts.delay(str(build.public_id), bool(build.image_uri))
    return "cancelled"


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def cleanup_failed_build_artifacts(self, build_id, delete_image=False):
    build = (
        Build.objects.select_related("project", "project__owner")
        .prefetch_related("input_assets")
        .filter(public_id=build_id)
        .first()
    )
    if not build:
        return "not_found"
    if build.status == "ready" or build.deletion_state != "active" or build.version_id:
        return "retained"
    if delete_image and build.image_uri:
        BuildImageCleaner().delete(build)
    storage = S3Storage()
    storage.delete_prefix(build_prefix(build.project.owner.tenant_id, build.project.public_id, build.public_id))
    build.input_assets.update(s3_uri="", purged_at=timezone.now())
    return "purged"


@shared_task(bind=True, max_retries=5)
def delete_build(self, build_id):
    """Keep the tombstone until external cleanup succeeds; repeated DELETE retries it."""
    from apps.catalog.models import ModelProject

    candidate = Build.objects.filter(public_id=build_id).first()
    if not candidate:
        return "deleted"
    try:
        with transaction.atomic():
            ModelProject.objects.select_for_update().get(pk=candidate.project_id)
            build = (
                Build.objects.select_for_update().select_related("project__owner").filter(public_id=build_id).first()
            )
            if not build:
                return "deleted"
            if build.deletion_state == "active":
                return "retained"
            if (
                build.version_id
                or build.registration_status in {"registering", "registered"}
                or build.deployments.exists()
            ):
                raise RuntimeError("Registered builds must be retained.")
            stop_build_for_deletion(build)
            # Use the server-generated build tag even if the runner failed before
            # reporting image_uri. Never delete a caller-supplied repository/digest.
            build.image_uri = temporary_image_reference(
                build.project.public_id,
                build.public_id,
                registry=settings.HARBOR_REGISTRY_URL if build.backend == "argo" else "",
                registry_project=settings.HARBOR_USER_PROJECT,
            )
            BuildImageCleaner().delete(build)
            S3Storage().delete_prefix(
                f"{build_prefix(build.project.owner.tenant_id, build.project.public_id, build.public_id).rstrip('/')}/"
            )
            build.delete()
        return "deleted"
    except Exception as exc:
        Build.objects.filter(public_id=build_id).update(
            deletion_state="delete_failed", deletion_error="Build cleanup failed; retry Delete or check worker logs."
        )
        logger.warning("Build cleanup failed for %s (%s).", build_id, type(exc).__name__)
        raise self.retry(exc=exc, countdown=min(10 * 2**self.request.retries, 120)) from exc


@shared_task(
    bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_jitter=True, max_retries=5
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
            health_status="unknown", last_checked_at=None, health_check_token=None, health_check_lease_until=None,
        )
        return "stopped"
    deployment.refresh_from_db()
    if deployment.status in {"succeeded", "failed", "stopped", "unconfirmed"}:
        if deployment.status == "stopped":
            backend.stop(deployment)
        return deployment.status
    append_deployment_log(deployment, "Runtime resource dispatched; waiting for readiness confirmation.")
    record_transition(deployment, "deploying", phase="dispatched")
    if endpoint.health_status == "healthy":
        _mark_deployment_succeeded(deployment)
        deployment.refresh_from_db()
        return deployment.status
    if deployment.backend == "argo":
        mark_deployment_unconfirmed.apply_async(args=[str(deployment.public_id)], countdown=33 * 60)
    else:
        check_deployment_health.apply_async(args=[str(deployment.public_id)], countdown=10)
    return "deploying"


@shared_task
def mark_deployment_unconfirmed(deployment_id):
    with transaction.atomic():
        deployment = Deployment.objects.select_for_update().select_related("version").get(public_id=deployment_id)
        if deployment.status != "deploying" or deployment.backend != "argo":
            return deployment.status
        deployment.status = "unconfirmed"
        deployment.error_message = "No deployment result callback arrived before the deadline. Check the workflow logs."
        deployment.save(update_fields=["status", "error_message", "updated_at"])
        invalidate_model_server_cache(str(deployment.version.public_id))
        append_deployment_log(deployment, deployment.error_message)
        record_transition(deployment, "unconfirmed", reason="Deployment result callback timed out")
        enqueue_event(
            topic="deployment.events",
            aggregate_type="deployment",
            aggregate_id=deployment.public_id,
            event_type="deployment.changed",
            payload={"deployment_id": str(deployment.public_id), "status": "unconfirmed"},
        )
    return "unconfirmed"


@shared_task(bind=True, max_retries=30)
def check_deployment_health(self, deployment_id):
    deployment = Deployment.objects.select_related("version", "build").get(public_id=deployment_id)
    if deployment.status != "deploying":
        return deployment.status
    healthy, metadata = deployment_backend(deployment.backend).health(deployment)
    Endpoint.objects.filter(deployment=deployment, deployment__status="deploying").update(
        health_status="healthy" if healthy else "unhealthy",
        last_checked_at=timezone.now(),
        metadata=metadata,
    )
    if healthy:
        _mark_deployment_succeeded(deployment)
        deployment.refresh_from_db()
        return deployment.status
    if self.request.retries >= self.max_retries:
        invalidate_model_server_cache(str(deployment.version.public_id))
        changed = Deployment.objects.filter(pk=deployment.pk, status="deploying").update(
            status="failed", error_message="Endpoint readiness check timed out."
        )
        if not changed:
            deployment.refresh_from_db()
            return deployment.status
        append_deployment_log(deployment, "Endpoint readiness check timed out.")
        record_transition(deployment, "failed", reason="Endpoint readiness check timed out")
        return "failed"
    append_deployment_log(deployment, "Endpoint is not healthy yet; retrying health check.")
    raise self.retry(countdown=min(10 + self.request.retries * 2, 60))


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def stop_deployment(self, deployment_id):
    deployment = Deployment.objects.select_related("version", "build").get(public_id=deployment_id)
    deployment_backend(deployment.backend).stop(deployment)
    Deployment.objects.filter(pk=deployment.pk).update(status="stopped", stopped_at=timezone.now())
    Endpoint.objects.filter(deployment=deployment).update(
        health_status="unknown", last_checked_at=None, health_check_token=None, health_check_lease_until=None
    )
    from apps.catalog.models import ModelProject

    ModelProject.objects.filter(active_deployment=deployment).update(active_deployment=None)
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
