from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ModelProject
from apps.deployment.models import Build


def complete_build(
    build, *, image_uri, image_digest="", package_uri="", metrics=None, params=None, insights=None, requirements=None
):
    """Record a build result without publishing a registry version."""
    with transaction.atomic():
        ModelProject.objects.select_for_update().get(pk=build.project_id)
        build = Build.objects.select_for_update().select_related("project").get(pk=build.pk)
        if build.status in {"ready", "cancelled", "failed"}:
            return build
        build.status = (
            "ready" if build.project.deletion_state == "active" and build.deletion_state == "active" else "cancelled"
        )
        build.image_uri = image_uri
        build.image_digest = image_digest
        build.package_uri = package_uri or build.package_uri
        build.metrics_summary = {**build.metrics_summary, **(metrics or {})}
        build.params_summary = {**build.params_summary, **(params or {})}
        build.insights_summary = {**build.insights_summary, **(insights or {})}
        if requirements is not None:
            build.requirements_snapshot = requirements
        build.completed_at = timezone.now()
        build.execution_completed_at = build.completed_at
        build.save()
    return build


def request_registration(build):
    from apps.deployment.tasks import register_build
    from common.api.exceptions import Conflict

    with transaction.atomic():
        ModelProject.objects.select_for_update().get(pk=build.project_id)
        build = Build.objects.select_for_update().select_related("project").get(pk=build.pk)
        if build.status != "ready" or build.project.deletion_state != "active" or build.deletion_state != "active":
            raise Conflict("Only a successful build can be registered.")
        if build.version_id or (
            build.registration_status == "registering" and build.updated_at > timezone.now() - timedelta(minutes=10)
        ):
            return build
        build.registration_status = "registering"
        build.registration_error = ""
        build.save(update_fields=["registration_status", "registration_error", "updated_at"])
        transaction.on_commit(lambda: register_build.delay(str(build.public_id)))
    return build
