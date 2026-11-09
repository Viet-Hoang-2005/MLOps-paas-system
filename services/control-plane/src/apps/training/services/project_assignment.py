"""Attach a completed job without changing its immutable model or storage."""

from django.db import transaction
from django.shortcuts import get_object_or_404

from apps.catalog.models import ModelProject
from apps.catalog.services.project_metadata import save_project_metadata
from apps.observability.services.lifecycle import record_training_event
from apps.training.models import TrainingJob
from apps.training.services.outputs import verify_training_output
from common.api.exceptions import Conflict


def assign_project(*, job, actor, data):
    project_data = data.get("new_project")
    project_uuid = data.get("project_id") or project_data["id"]
    if job.status != "completed" or job.outputs_purged_at or not job.outputs.filter(kind="model", s3_uri=job.output_uri).exists():
        raise Conflict("A completed job with an available model is required.")
    verify_training_output(job)
    with transaction.atomic():
        project = ModelProject.objects.select_for_update().filter(public_id=project_uuid, owner=actor).first()
        if project is None:
            if not project_data:
                get_object_or_404(ModelProject.objects.filter(owner=actor), public_id=project_uuid)
            if ModelProject.objects.filter(public_id=project_uuid).exists():
                raise Conflict("This project identifier is unavailable.")
            project = save_project_metadata(actor=actor, validated_data={
                "project_id": project_uuid, "name": project_data["name"],
                "description": project_data["description"], "access_mode": project_data["access_mode"],
            })
        if not project.is_active or project.deletion_state != "active":
            raise Conflict("This project is unavailable.")
        if project_data and (project.name != project_data["name"] or
                             project.description != project_data["description"] or
                             project.access_mode != project_data["access_mode"]):
            raise Conflict("The project identifier already belongs to a different project.")
        job = TrainingJob.objects.select_for_update().get(pk=job.pk, owner=actor)
        if job.project_id:
            if job.project_id == project.pk:
                return job
            raise Conflict("This job is already assigned to another project.")
        if job.status != "completed" or job.outputs_purged_at or not job.outputs.filter(kind="model", s3_uri=job.output_uri).exists():
            raise Conflict("A completed job with an available model is required.")
        if job.output_revision != data["output_revision"]:
            raise Conflict("Revision conflict. Reload the training output before saving.")
        job.project = project
        job.save(update_fields=["project", "updated_at"])
        record_training_event(job=job, event_type="project_assigned", message="Training job assigned to a model project.")
        return job
