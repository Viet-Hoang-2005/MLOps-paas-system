from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ModelProject
from apps.deployment.models import Deployment
from apps.deployment.services.cache import invalidate_model_server_cache
from common.logging import record_transition
from infrastructure.execution.cleanup_backends import project_cleanup_backend
from infrastructure.execution.image_references import temporary_image_reference
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import project_prefix


def request_project_deletion(project):
    """Disable a project before retryable hard cleanup."""
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
            else f"deploy-{deployment.public_id}"
            for deployment in deployments
        }
    )
    from apps.drift.models import DriftRun

    jobs = [
        *[f"build-{build.public_id}" for build in builds],
        *[f"training-{value}" for value in project.training_jobs.values_list("public_id", flat=True)],
        *[
            f"drift-{value}"
            for value in DriftRun.objects.filter(monitor__version__project=project).values_list("public_id", flat=True)
        ],
    ]
    return {"container_names": container_names, "job_container_names": jobs, "image_uris": image_uris}


def run_project_cleanup(project):
    if project.deletion_state != "deleting":
        raise ValidationError({"project": "Project deletion is not active."})
    _stop_project_jobs(project)
    return project_cleanup_backend().run(project, project_cleanup_manifest(project))


def _stop_project_jobs(project):
    from infrastructure.execution import build_backend, training_backend, drift_backend
    from apps.drift.models import DriftRun

    for build in project.builds.exclude(status__in=("ready", "failed", "cancelled")):
        result = build_backend(build.backend).cancel(build)
        if build.backend == "argo" and (not isinstance(result, dict) or not result.get("confirmed")):
            raise ValidationError("Wait for the active build workflow to finish before retrying cleanup.")
        type(build).objects.filter(pk=build.pk).update(status="cancelled", completed_at=timezone.now())
    for job in project.training_jobs.exclude(status__in=("completed", "failed", "cancelled")):
        result = training_backend(job.backend).cancel(job)
        if isinstance(result, dict) and not result.get("confirmed", False):
            raise ValidationError("Training cancellation has not completed; retry project cleanup.")
        type(job).objects.filter(pk=job.pk).update(status="cancelled", completed_at=timezone.now())
    for run in DriftRun.objects.filter(monitor__version__project=project).exclude(
        status__in=("completed", "failed", "cancelled")
    ):
        backend = drift_backend(run.monitor.backend)
        if not hasattr(backend, "cancel"):
            raise ValidationError("Cancel running drift workflows before retrying project cleanup.")
        backend.cancel(run)
        type(run).objects.filter(pk=run.pk).update(status="cancelled", completed_at=timezone.now())


def delete_project_build_images(project):
    """Run after Argo has confirmed all project runtimes were removed."""
    if project.deletion_state != "deleting":
        raise ValidationError({"project": "Project deletion is not active."})
    return project_cleanup_backend().delete_images(project, project_cleanup_manifest(project))


def finalize_project_deletion(project, *, storage=None):
    """Remove owned objects and DB aggregates, leaving unrelated projects untouched."""
    storage = storage or S3Storage()
    storage.delete_prefix(project_prefix(project.owner.tenant_id, project.public_id))
    with transaction.atomic():
        project = ModelProject.objects.select_for_update().get(pk=project.pk)
        from apps.ct import models as ct
        from apps.drift.models import DriftMonitor, DriftRun
        from apps.registry.models import RegistryAlias
        from apps.observability.models import EventOutbox, LifecycleEvent
        from common.redis_client import redis_client

        aggregates = [
            project.public_id,
            *project.versions.values_list("public_id", flat=True),
            *project.builds.values_list("public_id", flat=True),
            *project.training_jobs.values_list("public_id", flat=True),
            *Deployment.objects.filter(version__project=project).values_list("public_id", flat=True),
            *DriftRun.objects.filter(monitor__version__project=project).values_list("public_id", flat=True),
        ]
        redis = redis_client()
        keys = [
            *[f"build_logs:{value}" for value in project.builds.values_list("public_id", flat=True)],
            *[f"training_logs:{value}" for value in project.training_jobs.values_list("public_id", flat=True)],
            *[
                f"deployment_logs:{value}"
                for value in Deployment.objects.filter(version__project=project).values_list("public_id", flat=True)
            ],
            *[
                f"drift_logs:{value}"
                for value in DriftRun.objects.filter(monitor__version__project=project).values_list(
                    "public_id", flat=True
                )
            ],
        ]
        if keys:
            redis.delete(*keys)
        for version_id in project.versions.values_list("public_id", flat=True):
            invalidate_model_server_cache(str(version_id))
        ct.EvaluationGate.objects.filter(run__project=project).delete()
        ct.MaintenanceRun.objects.filter(project=project).delete()
        ct.MaintenanceDecision.objects.filter(window__project=project).delete()
        ct.Feedback.objects.filter(prediction__project=project).delete()
        ct.LabelLedgerEntry.objects.filter(budget__project=project).delete()
        ct.LabelRequest.objects.filter(window__project=project).delete()
        ct.EvidenceWindow.objects.filter(project=project).delete()
        ct.DatasetSnapshot.objects.filter(project=project).delete()
        ct.LabelBudget.objects.filter(project=project).delete()
        ct.MaintenancePolicy.objects.filter(project=project).delete()
        DriftMonitor.objects.filter(version__project=project).delete()
        RegistryAlias.objects.filter(project=project).delete()
        Deployment.objects.filter(version__project=project).delete()
        EventOutbox.objects.filter(aggregate_id__in=aggregates).delete()
        LifecycleEvent.objects.filter(project=project).delete()
        record_transition(project, "deleted")
        project.delete()
    return project


def mark_project_deletion_failed(project, error):
    project.deletion_state = "delete_failed"
    project.deletion_error = str(error)[:12000]
    project.save(update_fields=["deletion_state", "deletion_error", "updated_at"])
    record_transition(
        project,
        "delete_failed",
        reason="Project cleanup failed",
        error_type=type(error).__name__ if isinstance(error, Exception) else None,
        exc_info=(type(error), error, error.__traceback__) if isinstance(error, Exception) else None,
    )
    return project
