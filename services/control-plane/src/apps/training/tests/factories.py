"""Explicit workspace ownership for execution-only test fixtures."""

from apps.training.models import TrainingJob, TrainingWorkspace


def training_job(*, persist=True, **values):
    if "workspace" not in values and "workspace_id" not in values:
        owner = values.get("owner")
        if owner is None and values.get("project") is not None:
            owner = values["project"].owner
        if owner is None and values.get("owner_id"):
            from django.contrib.auth import get_user_model

            owner = get_user_model().objects.get(pk=values["owner_id"])
        values["workspace"] = TrainingWorkspace.objects.create(owner=owner)
    job = TrainingJob(**values)
    if persist:
        job.save()
    return job


def unsaved_training_job(**values):
    return training_job(persist=False, **values)
