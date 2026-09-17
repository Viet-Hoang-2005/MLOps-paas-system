from celery import shared_task
from common.logging import record_transition

from apps.catalog.models import ModelProject


@shared_task(bind=True)
def execute_project_deletion(self, project_id):
    from apps.catalog.services.deletion import (
        finalize_project_deletion,
        mark_project_deletion_failed,
        run_project_cleanup,
    )

    project = ModelProject.objects.select_related("owner").get(public_id=project_id)
    if project.deletion_state != "deleting":
        return project.deletion_state
    try:
        result = run_project_cleanup(project)
    except Exception as exc:
        mark_project_deletion_failed(project, exc)
        raise
    if result.get("dispatched"):
        record_transition(project, "deleting", phase="deletion_dispatched")
        return "deleting"
    finalize_project_deletion(project)
    return "deleted"


@shared_task(bind=True)
def complete_project_deletion(self, project_id):
    """Complete an Argo deletion only after its runtime stop callback is trusted."""
    from apps.catalog.services.deletion import (
        delete_project_build_images,
        finalize_project_deletion,
        mark_project_deletion_failed,
    )

    project = ModelProject.objects.select_related("owner").get(public_id=project_id)
    if project.deletion_state != "deleting":
        return project.deletion_state
    try:
        delete_project_build_images(project)
        finalize_project_deletion(project)
    except Exception as exc:
        mark_project_deletion_failed(project, exc)
        raise
    return "deleted"
