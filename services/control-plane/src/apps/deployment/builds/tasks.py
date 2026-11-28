import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.deployment.builds.cleanup import cleanup_failed_build_artifacts
from apps.deployment.models import Build
from apps.registry.versions.registration import register_successful_build
from common.telemetry.logging import failure_reported, record_transition
from infrastructure.execution import build_backend

logger = logging.getLogger(__name__)


@shared_task(name="apps.deployment.tasks.execute_build", bind=True)
def execute_build(self, build_id):
    candidate = Build.objects.filter(public_id=build_id).first()
    if not candidate:
        return "not_found"
    with transaction.atomic():
        from apps.catalog.models import ModelProject

        ModelProject.objects.select_for_update().get(pk=candidate.project_id)
        build = (
            Build.objects.select_for_update(of=("self",))
            .select_related("project", "project__owner")
            .get(public_id=build_id)
        )
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
        if build.backend == "docker":
            Build.objects.filter(pk=build.pk).update(
                execution_deadline_at=build.execution_deadline_at
                or timezone.now() + timedelta(seconds=settings.LOCAL_BUILD_TIMEOUT_SECONDS),
                next_execution_check_at=timezone.now(),
            )
        elif build.backend == "argo":
            Build.objects.filter(pk=build.pk).update(
                execution_deadline_at=build.execution_deadline_at
                or timezone.now() + timedelta(seconds=min(settings.LOCAL_BUILD_TIMEOUT_SECONDS, 14400)),
                next_execution_check_at=timezone.now(),
            )
        record_transition(build, "building")
    try:
        result = build_backend(build.backend).run(build)
    except Exception as exc:
        if not Build.objects.filter(pk=build.pk, deletion_state="active").exists():
            Build.objects.filter(pk=build.pk).update(status="cancelled", completed_at=timezone.now())
            return "cancelled"
        already_failed = Build.objects.filter(pk=build.pk, status="failed").exists()
        now = timezone.now()
        fields = {"next_execution_check_at": now} if build.backend == "argo" else {}
        Build.objects.filter(pk=build.pk).exclude(status__in=("cancelled", "ready")).update(
            status="failed", error_message=str(exc)[:12000], completed_at=now, **fields
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
    if isinstance(result, dict) and result.get("cancelled"):
        return "cancelled"
    if isinstance(result, dict) and result.get("dispatched"):
        build.refresh_from_db()
        if build.status != "building":
            return build.status
        record_transition(build, "building", phase="dispatched")
        return "building"
    raise RuntimeError("Build backend must return a dispatched execution.")


@shared_task(name="apps.deployment.tasks.register_build")
def register_build(build_id):
    build = Build.objects.select_related("project").filter(public_id=build_id).first()
    if not build:
        return "not_found"
    if build.version_id:
        return "registered"
    if not build.image_uri:
        Build.objects.filter(pk=build.pk, image_uri="", registration_status="registering").update(
            registration_status="unregistered", registration_error=""
        )
        return "image_missing"
    try:
        registered = register_successful_build(build=build, image_uri=build.image_uri, image_digest=build.image_digest)
    except Exception as exc:
        Build.objects.filter(pk=build.pk, version__isnull=True).exclude(image_uri="").update(
            registration_status="failed", registration_error=str(exc)[:12000]
        )
        raise
    # Another worker may still hold this build; it finishes (or fails) the registration.
    return "registered" if registered.version_id else "in_progress"


@shared_task(
    name="apps.deployment.tasks.cancel_build",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    reject_on_worker_lost=True,
)
def cancel_build(self, build_id):
    build = Build.objects.select_related("project").filter(public_id=build_id).first()
    if not build or build.deletion_state != "active":
        return "deleting"
    if build.backend == "argo":
        if build.status != "cancelled":
            return build.status
        if Build.objects.filter(pk=build.pk, status="cancelled", completed_at__isnull=True).update(
            completed_at=timezone.now()
        ):
            record_transition(build, "cancelled")
        cleanup_failed_build_artifacts.delay(build_id, bool(build.image_uri))
        return "cancelled"
    build_backend(build.backend).cancel(build)
    Build.objects.filter(pk=build.pk).update(status="cancelled", completed_at=timezone.now())
    record_transition(build, "cancelled")
    cleanup_failed_build_artifacts.delay(str(build.public_id), bool(build.image_uri))
    return "cancelled"
