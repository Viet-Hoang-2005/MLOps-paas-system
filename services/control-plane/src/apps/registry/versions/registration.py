import uuid
from contextlib import contextmanager
from dataclasses import dataclass

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.observability.lifecycle import record_registry_event
from apps.registry.models import ModelArtifact, ModelMetric, ModelVersion
from infrastructure.images.references import repository_from_reference
from infrastructure.images.registry import image_registry_for
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import version_prefix


@contextmanager
def _registration_storage(storage):
    """Remove copied objects if publishing the database snapshot fails."""
    copied = []

    class TrackedStorage:
        def copy(self, uri, key):
            result = storage.copy(uri, key)
            copied.append(result.uri)
            return result

    try:
        yield TrackedStorage()
    except Exception:
        for uri in copied:
            storage.delete(uri)
        raise


BUILD_INPUT_ARTIFACT_KINDS = {
    "source_artifact": "source",
    "source_code": "source_code",
    "reference_data": "reference_data",
    "training_output": "training_output",
    "label_mapping": "label_mapping",
    "metrics": "metrics",
    "params": "params",
    "model_insights": "model_insights",
    "feature_importance": "feature_importance",
    "input_schema": "input_schema",
}


REGISTRATION_LOCK_SECONDS = 1800


class _AlreadyRegistered(Exception):
    def __init__(self, build):
        super().__init__("Build already registered.")
        self.build = build


@dataclass
class _RegistrationPlan:
    """Everything phase 2 needs, read under a short lock so no lock spans network I/O."""

    version_number: int
    version_public_id: uuid.UUID
    tenant_id: str
    project_public_id: uuid.UUID
    assets: list
    package_uri: str
    metrics_summary: dict
    params_summary: dict
    insights_summary: dict


def _plan_registration(build, metrics_summary, params_summary, insights_summary):
    """Phase 1: validate the build and reserve a version number. Returns (build, plan).

    ``plan`` is None when the build is already registered.
    """
    with transaction.atomic():
        project = type(build.project).objects.select_for_update().get(pk=build.project_id)
        build = (
            type(build).objects.select_for_update(of=("self",)).select_related("project", "project__owner").get(pk=build.pk)
        )
        if build.status != "ready" or project.deletion_state != "active" or build.deletion_state != "active":
            raise ValidationError({"build": "Only successful builds of active projects can be registered."})
        if build.version_id:
            return build, None
        if not build.image_uri:
            raise ValidationError({"build": "Rebuild the image before registering a model version."})
        version_number = project.next_version_number
        while ModelVersion.objects.filter(project=project, version=str(version_number)).exists():
            version_number += 1
        # Reserved now so the image tag chosen in phase 2 cannot collide with a
        # concurrent registration; released again if registration fails.
        project.next_version_number = version_number + 1
        project.save(update_fields=["next_version_number", "updated_at"])
        if build.registration_status != "registering":
            build.registration_status = "registering"
            build.registration_error = ""
            build.save(update_fields=["registration_status", "registration_error", "updated_at"])
        plan = _RegistrationPlan(
            version_number=version_number,
            version_public_id=uuid.uuid4(),
            tenant_id=project.owner.tenant_id,
            project_public_id=project.public_id,
            assets=list(build.input_assets.all()),
            package_uri=build.package_uri,
            metrics_summary=metrics_summary if metrics_summary is not None else build.metrics_summary,
            params_summary=params_summary if params_summary is not None else build.params_summary,
            insights_summary=insights_summary if insights_summary is not None else build.insights_summary,
        )
    return build, plan


def _release_version_number(build, version_number):
    """Give back a reserved number if nobody has reserved a later one meanwhile."""
    with transaction.atomic():
        project = type(build.project).objects.select_for_update().get(pk=build.project_id)
        if project.next_version_number == version_number + 1:
            project.next_version_number = version_number
            project.save(update_fields=["next_version_number", "updated_at"])


def register_successful_build(
    *,
    build,
    image_uri,
    image_digest="",
    metrics_summary=None,
    params_summary=None,
    insights_summary=None,
    storage=None,
    image_registry=None,
):
    """Idempotently publish a manual build as an immutable registry version.

    S3 copies and the image promotion are slow, so they run with no database lock:
    1. claim the build and reserve a version number (short lock),
    2. copy artifacts and promote the image (no lock),
    3. re-check and write the version rows (short lock).
    Copied objects are removed and the number released if a later step fails.
    """

    storage = storage or S3Storage()
    image_registry = image_registry or image_registry_for(build)
    # One registration per build at a time; the checks in phases 1 and 3 still decide
    # correctness if this lock ever expires.
    lock_key = f"register-build:{build.pk}"
    if not cache.add(lock_key, 1, timeout=REGISTRATION_LOCK_SECONDS):
        build.refresh_from_db()
        return build
    try:
        build, plan = _plan_registration(build, metrics_summary, params_summary, insights_summary)
        if plan is None:
            return build
        try:
            with _registration_storage(storage) as tracked:
                copies = _copy_registration_artifacts(build, plan, tracked)
                candidate = ModelVersion(
                    public_id=plan.version_public_id, project=build.project, version=str(plan.version_number)
                )
                version_image_uri, resolved_image_digest = image_registry.promote(
                    build=build, version=candidate, image_uri=image_uri, image_digest=image_digest
                )
                return _commit_registration(
                    build,
                    plan,
                    copies,
                    image_uri=image_uri,
                    version_image_uri=version_image_uri,
                    image_digest=resolved_image_digest,
                )
        except _AlreadyRegistered as done:
            _release_version_number(build, plan.version_number)
            return done.build
        except Exception:
            _release_version_number(build, plan.version_number)
            raise
    finally:
        cache.delete(lock_key)


def _copy_registration_artifacts(build, plan, storage):
    prefix = version_prefix(plan.tenant_id, plan.project_public_id, plan.version_public_id)
    copies = []
    for asset in plan.assets:
        stored = storage.copy(asset.s3_uri, f"{prefix}/artifacts/{asset.kind}/{asset.name}")
        copies.append((asset, stored))
    package = (
        storage.copy(plan.package_uri, f"{prefix}/artifacts/package/model-package.zip") if plan.package_uri else None
    )
    return copies, package


def _commit_registration(build, plan, copies, *, image_uri, version_image_uri, image_digest):
    """Phase 3: write the version, artifacts and build state under a short lock."""
    from apps.deployment.builds.registration import enqueue_registered_storage_cleanup

    asset_copies, package = copies
    with transaction.atomic():
        project = type(build.project).objects.select_for_update().get(pk=build.project_id)
        build = (
            type(build).objects.select_for_update(of=("self",)).select_related("project", "project__owner").get(pk=build.pk)
        )
        if build.version_id:
            # A concurrent registration finished first; keep its version, drop our copies.
            raise _AlreadyRegistered(build)
        if build.status != "ready" or project.deletion_state != "active" or build.deletion_state != "active":
            raise ValidationError({"build": "Only successful builds of active projects can be registered."})
        version = ModelVersion.objects.create(
            public_id=plan.version_public_id,
            project=project,
            source_job=build.source_job,
            source_job_reference=build.source_job_reference
            or (build.source_job.public_id if build.source_job_id else None),
            version=str(plan.version_number),
            requirements_snapshot=build.requirements_snapshot,
            flavor=build.flavor,
            deployability="deployable",
            metrics_summary=plan.metrics_summary or {},
            params_summary=plan.params_summary or {},
            insights_summary=plan.insights_summary or {},
        )
        for asset, stored in asset_copies:
            ModelArtifact.objects.create(
                version=version,
                kind=BUILD_INPUT_ARTIFACT_KINDS[asset.kind],
                name=asset.name,
                uri=stored.uri,
                checksum=stored.checksum,
                size_bytes=stored.size_bytes,
                content_type=stored.content_type,
                metadata={
                    "artifact_format": build.artifact_format,
                    "source_job_id": str(build.source_job_reference),
                }
                if asset.kind == "training_output"
                else {"artifact_format": build.artifact_format}
                if asset.kind == "source_artifact"
                else asset.metadata,
            )
        if package is not None:
            ModelArtifact.objects.create(
                version=version,
                kind="package",
                name="model-package.zip",
                uri=package.uri,
                checksum=package.checksum,
                size_bytes=package.size_bytes,
                content_type=package.content_type,
            )
        record_registry_event(
            version=version,
            actor=project.owner,
            event_type="registered",
            to_state=version.stage,
            metadata={
                "source": "training_job" if build.source_job_id else "manual_build",
                "build_id": str(build.public_id),
                "source_job_id": str(build.source_job.public_id) if build.source_job_id else None,
            },
        )
        for name, value in (plan.metrics_summary or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                ModelMetric.objects.create(version=version, name=str(name)[:160], value=float(value))

        identity_kind = "oci_manifest_digest" if build.backend == "argo" else "docker_image_id"
        ModelArtifact.objects.update_or_create(
            version=version,
            kind="image",
            name=version_image_uri.rsplit("/", 1)[-1],
            defaults={
                "uri": version_image_uri,
                "checksum": image_digest,
                "metadata": {
                    "build_id": str(build.public_id),
                    "temporary_image_uri": image_uri,
                    "repository": repository_from_reference(version_image_uri),
                    "identity_kind": identity_kind,
                },
            },
        )
        build.version = version
        build.image_uri = version_image_uri
        build.image_digest = image_digest
        build.status = "ready"
        build.error_message = ""
        build.registration_status = "registered"
        build.registration_error = ""
        build.registered_storage_cleanup_due_at = timezone.now()
        build.save(
            update_fields=[
                "version",
                "image_uri",
                "image_digest",
                "status",
                "error_message",
                "registration_status",
                "registration_error",
                "registered_storage_cleanup_due_at",
                "updated_at",
            ]
        )
        enqueue_registered_storage_cleanup(build)
    return build


_JSON_SUPPLEMENTAL_KINDS = (
    "label_mapping",
    "input_schema",
    "metrics",
    "params",
    "model_insights",
    "feature_importance",
)


_SUMMARY_OBJECT_KINDS = {"metrics", "params", "model_insights", "input_schema"}


_SNAPSHOT_SUMMARY_KINDS = {"metrics", "params", "model_insights", "feature_importance"}


_ARTIFACT_LABELS = {"source_code": "source code", "reference_data": "reference data"}


_MAX_SUPPLEMENTAL_JSON_BYTES = 4 * 1024 * 1024
