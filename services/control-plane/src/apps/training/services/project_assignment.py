"""Atomically attach a job and its explicitly selected artifacts."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from apps.catalog.models import ModelProject
from apps.catalog.services.project_metadata import save_project_metadata
from apps.observability.services.lifecycle import record_training_event
from apps.training.models import TrainingJob, TrainingOutput
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage
from .artifact_selection import prepare_selection


def assign_project(*, job, actor, data, files=None):
    if (
        job.owner_id != actor.pk
        or job.status != "completed"
        or job.outputs_purged_at
        or job.tracking.get("output_contract") != 2
    ):
        raise Conflict("A completed job with verified v2 outputs is required.")
    storage = S3Storage()
    selection, staged = prepare_selection(job, data, files or {}, storage)
    project_data = data.get("new_project")
    project_uuid = data.get("project_id") or project_data["id"]
    try:
        with transaction.atomic():
            project = ModelProject.objects.select_for_update().filter(public_id=project_uuid, owner=actor).first()
            if project is None:
                if not project_data:
                    get_object_or_404(ModelProject.objects.filter(owner=actor), public_id=project_uuid)
                if ModelProject.objects.filter(public_id=project_uuid).exists():
                    raise Conflict("This project identifier is unavailable.")
                project = save_project_metadata(
                    actor=actor,
                    validated_data={
                        "project_id": project_uuid,
                        "name": project_data["name"],
                        "description": project_data["description"],
                        "access_mode": project_data["access_mode"],
                    },
                )
            if not project.is_active or project.deletion_state != "active":
                raise Conflict("This project is unavailable.")
            if project_data and any(
                getattr(project, key) != project_data[key] for key in ("name", "description", "access_mode")
            ):
                raise Conflict("Project identifier belongs to a different request.")
            current = TrainingJob.objects.select_for_update().get(pk=job.pk, owner=actor)
            if current.project_id and current.project_id != project.pk:
                raise Conflict("This job is already assigned to another project.")
            if (
                current.status != "completed"
                or current.outputs_purged_at
                or current.tracking.get("output_contract") != 2
            ):
                raise Conflict("Training outputs are unavailable.")
            if (
                current.project_id == project.pk
                and current.artifact_selection.get("fingerprint") == selection["fingerprint"]
            ):
                return current
            if current.output_revision != data["output_revision"]:
                raise Conflict("Revision conflict. Reload before saving.")
            # Revalidate IDs under the job lock after storage I/O.
            identifiers = [
                selection["model_id"],
                *[v for v in selection["artifacts"].values() if v not in {str(a.public_id) for a in staged}],
            ]
            if current.outputs.filter(public_id__in=identifiers).count() != len(set(identifiers)):
                raise Conflict("Output selection changed while saving.")
            TrainingOutput.objects.bulk_create(staged)
            current.project = project
            current.artifact_selection = selection
            current.output_revision += 1
            current.save(update_fields=["project", "artifact_selection", "output_revision", "updated_at"])
            record_training_event(
                job=current, event_type="project_assigned", message="Project and artifact selection saved."
            )
            return current
    finally:
        for asset in staged:
            if not TrainingOutput.objects.filter(public_id=asset.public_id).exists():
                storage.delete(asset.s3_uri)
