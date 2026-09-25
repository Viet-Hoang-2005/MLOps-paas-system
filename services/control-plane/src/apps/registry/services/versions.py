from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.observability.services.lifecycle import record_registry_event
from apps.observability.services.outbox import enqueue_event
from apps.registry.models import ModelArtifact, ModelMetric, ModelVersion
from infrastructure.execution.image_references import repository_from_reference
from infrastructure.execution.image_registry import image_registry_for
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_prefix, version_prefix

BUILD_INPUT_ARTIFACT_KINDS = {
    "model": "model",
    "label_mapping": "label_mapping",
    "metrics": "metrics",
    "params": "params",
    "model_insights": "model_insights",
    "feature_importance": "feature_importance",
    "input_schema": "input_schema",
    "reference_data": "reference_data",
    "source_code": "source_code",
    "data_contract": "data_contract",
}


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
    """Publish a completed build as an immutable registry version."""

    storage = storage or S3Storage()
    image_registry = image_registry or image_registry_for(build)
    with transaction.atomic():
        build = type(build).objects.select_for_update().select_related("project", "project__owner").get(pk=build.pk)
        project = type(build.project).objects.select_for_update().get(pk=build.project_id)
        if build.version_id is None:
            version_number = project.next_version_number
            while ModelVersion.objects.filter(project=project, version=str(version_number)).exists():
                version_number += 1
            ref_input_asset = build.input_assets.filter(kind="reference_data").first()
            if build.source_version_id:
                reference_snapshot = build.source_version.reference_snapshot
                if not reference_snapshot:
                    raise ValidationError({"reference_data": "Source version has no immutable reference snapshot."})
            elif ref_input_asset is None:
                raise ValidationError({"reference_data": "Build must include reference data before registration."})
            else:
                from apps.ct.models import DatasetSnapshot
                version_public_id = uuid.uuid4()
                ref_key = f"{version_prefix(project.owner.tenant_id, project.public_id, version_public_id)}/artifacts/reference_data/{ref_input_asset.name}"
                stored_reference = storage.copy(ref_input_asset.s3_uri, ref_key)
                reference_snapshot = DatasetSnapshot.objects.create(
                    project=project, role="reference", manifest_uri=stored_reference.uri,
                    manifest_checksum=stored_reference.checksum or ref_input_asset.checksum or "", schema_checksum="", row_count=0,
                    metadata={"source_build_id": str(build.public_id), "name": ref_input_asset.name},
                    sealed_at=timezone.now(),
                )
            if build.source_version_id:
                version_public_id = uuid.uuid4()
            version = ModelVersion.objects.create(
                public_id=version_public_id,
                project=project,
                source_job=build.source_job,
                source_job_reference=build.source_job.public_id if build.source_job_id else None,
                version=str(version_number),
                requirements_snapshot=build.requirements_snapshot,
                flavor=build.flavor,
                deployability="deployable",
                metrics_summary=metrics_summary if metrics_summary is not None else build.metrics_summary,
                params_summary=params_summary if params_summary is not None else build.params_summary,
                insights_summary=insights_summary if insights_summary is not None else build.insights_summary,
                reference_snapshot=reference_snapshot,
            )
            for asset in build.input_assets.all():
                destination_key = (
                    f"{version_prefix(project.owner.tenant_id, project.public_id, version.public_id)}"
                    f"/artifacts/{asset.kind}/{asset.name}"
                )
                if asset.kind == "reference_data" and not build.source_version_id:
                    stored = stored_reference
                else:
                    stored = storage.copy(asset.s3_uri, destination_key)
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
                        "source_job_id": str(build.source_job.public_id) if build.source_job_id else None,
                    }
                    if build.source_job_id and asset.kind == "model" else {"artifact_format": build.artifact_format},
                )
            if build.package_uri:
                package_name = "model-package.zip"
                package_key = (
                    f"{version_prefix(project.owner.tenant_id, project.public_id, version.public_id)}"
                    f"/artifacts/package/{package_name}"
                )
                package = storage.copy(build.package_uri, package_key)
                ModelArtifact.objects.create(
                    version=version,
                    kind="package",
                    name=package_name,
                    uri=package.uri,
                    checksum=package.checksum,
                    size_bytes=package.size_bytes,
                    content_type=package.content_type,
                )
            project.next_version_number = version_number + 1
            project.save(update_fields=["next_version_number", "updated_at"])
            record_registry_event(
                version=version,
                actor=project.owner,
                event_type="registered",
                to_state="registered",
                metadata={
                    "source": build.source_kind,
                    "build_id": str(build.public_id),
                    "source_job_id": str(build.source_job.public_id) if build.source_job_id else None,
                },
            )
            for name, value in (metrics_summary or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    ModelMetric.objects.create(version=version, name=str(name)[:160], value=float(value))
            build.version = version
        else:
            version = build.version

        version_image_uri, resolved_image_digest = image_registry.promote(
            build=build,
            version=version,
            image_uri=image_uri,
            image_digest=image_digest,
        )
        identity_kind = "oci_manifest_digest" if build.backend == "argo" else "docker_image_id"

        ModelArtifact.objects.update_or_create(
            version=version,
            kind="image",
            name=version_image_uri.rsplit("/", 1)[-1],
            defaults={
                "uri": version_image_uri,
                "checksum": resolved_image_digest,
                "metadata": {
                    "build_id": str(build.public_id),
                    "temporary_image_uri": image_uri,
                    "repository": repository_from_reference(version_image_uri),
                    "identity_kind": identity_kind,
                },
            },
        )
        build.image_uri = version_image_uri
        build.image_digest = resolved_image_digest
        build.status = "ready"
        build.error_message = ""
        build.save(
            update_fields=[
                "version",
                "image_uri",
                "image_digest",
                "status",
                "error_message",
                "updated_at",
            ]
        )
        # Synchronize draft ONLY if build was sourced from draft
        if (
            build.source_draft_revision_id
            and hasattr(project, "draft")
            and project.draft.locked_by_build_id == build.id
        ):
            project.draft.locked_by_build = None
            snapshot = build.source_draft_revision
            project.draft.assets.all().delete()
            from apps.catalog.models import DraftAsset
            DraftAsset.objects.bulk_create([
                DraftAsset(draft=project.draft, kind=item.kind, name=item.name, s3_uri=item.uri,
                           checksum=item.checksum, size_bytes=item.size_bytes, content_type=item.content_type,
                           metadata=item.metadata)
                for item in snapshot.assets.all()
            ])
            project.draft.flavor = snapshot.flavor
            project.draft.artifact_format = snapshot.artifact_format
            project.draft.requirements_snapshot = snapshot.requirements_snapshot
            project.draft.source_version = snapshot.source_version
            project.draft.revision += 1
            project.draft.saved_revision = project.draft.revision
            project.draft.status = "ready"
            project.draft.saved_at = timezone.now()
            project.draft.save(
                update_fields=["locked_by_build", "flavor", "artifact_format", "requirements_snapshot", "source_version", "revision", "status", "saved_revision", "saved_at", "updated_at"]
            )

        transaction.on_commit(
            lambda: storage.delete_prefix(build_prefix(project.owner.tenant_id, project.public_id, build.public_id))
        )
    return build


def set_alias(*, project, actor, name, version):
    from apps.deployment.models import Deployment
    from apps.registry.models import RegistryAlias

    if version.project_id != project.id:
        raise ValidationError({"version": "The version belongs to another project."})

    if name == "production":
        healthy_deployment = Deployment.objects.filter(
            version=version, target="production", status="healthy", endpoint__health_status="healthy"
        ).exists()
        if not healthy_deployment:
            raise ValidationError(
                {"version": "Cannot promote to production: version has no healthy active deployment."}
            )

    alias, _ = RegistryAlias.objects.update_or_create(project=project, name=name, defaults={"version": version})
    record_registry_event(version=version, actor=actor, event_type="alias_updated", to_state=name)
    enqueue_event(
        topic="registry.events",
        aggregate_type="model_project",
        aggregate_id=project.public_id,
        event_type="model.promoted",
        payload={
            "project_id": str(project.public_id),
            "version_id": str(version.public_id),
            "alias": name,
        },
    )
    return alias


def request_version_rebuild(*, version, actor, backend="docker", storage=None):
    """
    Rebuild an existing ModelVersion as a new Build without mutating the user's ModelDraft.
    Clones all immutable artifacts from the version and carries over the reference_snapshot.
    """
    from apps.deployment.models import Build, BuildInputAsset
    from infrastructure.storage.paths import build_input_prefix

    storage = storage or S3Storage()
    with transaction.atomic():
        version = (
            ModelVersion.objects.select_for_update()
            .select_related("project", "project__owner", "reference_snapshot")
            .prefetch_related("artifacts")
            .get(pk=version.pk)
        )
        project = version.project

        build = Build.objects.create(
            project=project,
            source_version=version,
            flavor=version.flavor,
            artifact_format="model_version",
            requirements_snapshot=version.requirements_snapshot,
            metrics_summary=version.metrics_summary,
            params_summary=version.params_summary,
            insights_summary=version.insights_summary,
            backend=backend,
            status="pending",
        )
        try:
            for artifact in version.artifacts.all():
                if artifact.kind in (
                    "image",
                    "package",
                    "metrics",
                    "params",
                    "model_insights",
                    "feature_importance",
                    "input_schema",
                ):
                    continue

                input_kind = artifact.kind
                if input_kind == "source":
                    input_kind = "source_code"
                input_prefix = build_input_prefix(
                    project.owner.tenant_id,
                    project.public_id,
                    build.public_id,
                    input_kind,
                )
                destination_key = f"{input_prefix}{artifact.name}"
                stored = storage.copy(artifact.uri, destination_key)
                BuildInputAsset.objects.create(
                    build=build,
                    kind=input_kind,
                    name=artifact.name,
                    s3_uri=stored.uri,
                    checksum=stored.checksum or artifact.checksum,
                    size_bytes=stored.size_bytes or artifact.size_bytes,
                    content_type=stored.content_type or artifact.content_type,
                )
        except Exception:
            storage.delete_prefix(build_prefix(project.owner.tenant_id, project.public_id, build.public_id))
            raise

        build.status = "queued"
        build.save(update_fields=["status", "updated_at"])
        transaction.on_commit(lambda: _enqueue_rebuild(build))
        return build


def _enqueue_rebuild(build):
    from apps.deployment.models import Build
    from apps.deployment.tasks import execute_build

    result = execute_build.delay(str(build.public_id))
    Build.objects.filter(pk=build.pk).update(celery_task_id=result.id)

import uuid
import uuid
