from celery import shared_task

from apps.catalog.models import ModelProject
from common.logging import record_transition


@shared_task(bind=True, reject_on_worker_lost=True)
def execute_project_deletion(self, project_id):
    from apps.catalog.services.deletion import (
        finalize_project_deletion,
        mark_project_deletion_failed,
        run_project_cleanup,
    )

    project = ModelProject.objects.select_related("owner").filter(public_id=project_id).first()
    if project is None:
        return "deleted"
    if project.deletion_state != "deleting":
        return project.deletion_state
    try:
        result = run_project_cleanup(project)
        if result.get("waiting_for_stop"):
            return "deleting"
        if not result.get("dispatched"):
            finalize_project_deletion(project)
    except Exception as exc:
        mark_project_deletion_failed(project, exc)
        raise
    if result.get("dispatched"):
        record_transition(project, "deleting", phase="deletion_dispatched")
        return "deleting"
    return "deleted"


@shared_task(bind=True, reject_on_worker_lost=True)
def complete_project_deletion(self, project_id):
    """Complete an Argo deletion only after its runtime stop callback is trusted."""
    from apps.catalog.services.deletion import (
        delete_project_build_images,
        finalize_project_deletion,
        mark_project_deletion_failed,
    )
    from apps.observability.services.argo_stops import project_has_unconfirmed_argo_stops

    project = ModelProject.objects.select_related("owner").filter(public_id=project_id).first()
    if project is None:
        return "deleted"
    if project.deletion_state != "deleting":
        return project.deletion_state
    if project_has_unconfirmed_argo_stops(project):
        return "deleting"
    try:
        delete_project_build_images(project)
        finalize_project_deletion(project)
    except Exception as exc:
        mark_project_deletion_failed(project, exc)
        raise
    return "deleted"
