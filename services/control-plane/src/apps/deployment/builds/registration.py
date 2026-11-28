import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ModelProject
from apps.deployment.models import Build
from infrastructure.images.references import temporary_image_reference


def expected_build_image(build):
    return temporary_image_reference(
        build.project.public_id,
        build.public_id,
        registry=settings.HARBOR_REGISTRY_URL if build.backend == "argo" else "",
        registry_project=settings.HARBOR_USER_PROJECT,
    )


def valid_build_result(build, payload, expected_image):
    return (
        payload.get("image_uri") == expected_image
        and re.fullmatch(r"sha256:[a-f0-9]{64}", str(payload.get("image_digest", "")))
        and isinstance(payload.get("package_manifest"), dict)
        and bool(payload["package_manifest"])
        and bool(build.package_uri)
        and payload.get("package_uri", build.package_uri) == build.package_uri
    )


def complete_reported_build(build, payload, expected_image):
    summaries = {
        field: payload[field] if isinstance(payload.get(field), dict) and not build.source_job_reference else None
        for field in ("metrics_summary", "params_summary", "insights_summary")
    }
    requirements = payload.get("requirements_snapshot")
    return complete_build(
        build,
        image_uri=expected_image,
        image_digest=str(payload["image_digest"]),
        metrics=summaries["metrics_summary"],
        params=summaries["params_summary"],
        insights=summaries["insights_summary"],
        requirements=requirements if isinstance(requirements, str) else None,
    )


def complete_build(
    build, *, image_uri, image_digest="", package_uri="", metrics=None, params=None, insights=None, requirements=None
):
    """Record a build result without publishing a registry version."""
    with transaction.atomic():
        ModelProject.objects.select_for_update().get(pk=build.project_id)
        build = Build.objects.select_for_update(of=("self",)).select_related("project").get(pk=build.pk)
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


def enqueue_registered_storage_cleanup(build):
    from apps.deployment.builds.cleanup import cleanup_registered_build_storage

    due_at = build.registered_storage_cleanup_due_at
    if due_at is not None and due_at <= timezone.now():
        transaction.on_commit(lambda: cleanup_registered_build_storage.delay(str(build.public_id)), robust=True)


def request_registration(build):
    from apps.deployment.builds.tasks import register_build
    from common.api.exceptions import Conflict

    with transaction.atomic():
        ModelProject.objects.select_for_update().get(pk=build.project_id)
        build = Build.objects.select_for_update(of=("self",)).select_related("project").get(pk=build.pk)
        if build.status != "ready" or build.project.deletion_state != "active" or build.deletion_state != "active":
            raise Conflict("Only a successful build can be registered.")
        if build.version_id:
            enqueue_registered_storage_cleanup(build)
            return build
        if not build.image_uri:
            raise Conflict("This build has no image. Rebuild it before registering a model version.")
        if build.registration_status == "registering" and build.updated_at > timezone.now() - timedelta(minutes=10):
            return build
        build.registration_status = "registering"
        build.registration_error = ""
        build.save(update_fields=["registration_status", "registration_error", "updated_at"])
        transaction.on_commit(lambda: register_build.delay(str(build.public_id)))
    return build
