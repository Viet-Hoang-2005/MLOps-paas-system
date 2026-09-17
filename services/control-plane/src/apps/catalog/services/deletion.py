from common.logging import record_transition
from django.db import transaction
from django.utils import timezone
from infrastructure.execution.cleanup_backends import project_cleanup_backend
from infrastructure.execution.image_references import temporary_image_reference
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import project_prefix
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ModelProject
from apps.deployment.models import Deployment, Endpoint
from apps.deployment.services.cache import invalidate_model_server_cache


def request_project_deletion(project):
    """Start an idempotent project-wide cleanup without deleting lifecycle audit rows."""
    with transaction.atomic():
        project = ModelProject.objects.select_for_update().get(pk=project.pk)
        if project.deletion_state == "deleted":
            return project
        if project.deletion_state == "deleting":
            return project
        if project.deletion_state == "delete_failed":
            project.deletion_error = ""
        project.deletion_state = "deleting"
        project.is_active = False
        project.save(update_fields=["deletion_state", "deletion_error", "is_active", "updated_at"])
        transaction.on_commit(lambda: _enqueue(project))
    return project


def _enqueue(project):
    from apps.catalog.tasks import execute_project_deletion

    result = execute_project_deletion.delay(str(project.public_id))
    ModelProject.objects.filter(pk=project.pk).update(deletion_task_id=result.id)


def project_cleanup_manifest(project):
    deployments = list(Deployment.objects.filter(version__project=project).select_related("build", "endpoint"))
    builds = list(project.builds.all())
    image_uris = sorted(
        {
            image_uri
            for build in builds
            for image_uri in (
                build.image_uri,
                temporary_image_reference(project.public_id, build.public_id),
            )
            if image_uri
        }
    )
    container_names = sorted(
        {
            getattr(deployment, "endpoint", None).runtime_name
            if getattr(deployment, "endpoint", None) and deployment.endpoint.runtime_name
            else f"deploy-{deployment.build.public_id}"
            for deployment in deployments
        }
    )
    return {"container_names": container_names, "image_uris": image_uris}


def run_project_cleanup(project):
    if project.deletion_state != "deleting":
        raise ValidationError({"project": "Project deletion is not active."})
    return project_cleanup_backend().run(project, project_cleanup_manifest(project))


def delete_project_build_images(project):
    """Run after Argo has confirmed all project runtimes were removed."""
    if project.deletion_state != "deleting":
        raise ValidationError({"project": "Project deletion is not active."})
    return project_cleanup_backend().delete_images(project, project_cleanup_manifest(project))


def finalize_project_deletion(project, *, storage=None):
    """Remove tenant project objects from S3 and retain DB rows as a deleted audit record."""
    storage = storage or S3Storage()
    storage.delete_prefix(project_prefix(project.owner.tenant_id, project.public_id))
    with transaction.atomic():
        project = ModelProject.objects.select_for_update().get(pk=project.pk)
        Deployment.objects.filter(version__project=project).exclude(status="stopped").update(
            status="stopped",
            stopped_at=timezone.now(),
        )
        Endpoint.objects.filter(deployment__version__project=project).update(health_status="stopped")
        for version_id in project.versions.values_list("public_id", flat=True):
            invalidate_model_server_cache(str(version_id))
        project.deletion_state = "deleted"
        project.deletion_error = ""
        project.deletion_task_id = ""
        project.deleted_at = timezone.now()
        project.is_active = False
        project.save(
            update_fields=[
                "deletion_state",
                "deletion_error",
                "deletion_task_id",
                "deleted_at",
                "is_active",
                "updated_at",
            ]
        )
        record_transition(project, "deleted")
    return project


def mark_project_deletion_failed(project, error):
    project.deletion_state = "delete_failed"
    project.deletion_error = str(error)[:12000]
    project.save(update_fields=["deletion_state", "deletion_error", "updated_at"])
    record_transition(
        project, "delete_failed", reason="Project cleanup failed",
        error_type=type(error).__name__ if isinstance(error, Exception) else None,
        exc_info=(type(error), error, error.__traceback__) if isinstance(error, Exception) else None,
    )
    return project
