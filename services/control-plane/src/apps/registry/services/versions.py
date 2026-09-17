from django.db import transaction
from infrastructure.execution.image_references import repository_from_reference
from infrastructure.execution.image_registry import image_registry_for
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_prefix, version_prefix
from rest_framework.exceptions import ValidationError

from apps.observability.services.outbox import enqueue_event
from apps.observability.services.lifecycle import record_registry_event
from apps.registry.models import ModelArtifact, ModelMetric, ModelVersion

BUILD_INPUT_ARTIFACT_KINDS = {
    "source_artifact": "source",
    "training_output": "training_output",
    "label_mapping": "label_mapping",
    "metrics": "metrics",
    "params": "params",
    "model_insights": "model_insights",
    "feature_importance": "feature_importance",
    "input_schema": "input_schema",
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
    """Idempotently publish a manual build as an immutable registry version."""

    storage = storage or S3Storage()
    image_registry = image_registry or image_registry_for(build)
    with transaction.atomic():
        build = (
            type(build)
            .objects.select_for_update()
            .select_related("project", "project__owner")
            .get(pk=build.pk)
        )
        project = type(build.project).objects.select_for_update().get(pk=build.project_id)
        if build.version_id is None:
            version_number = project.next_version_number
            while ModelVersion.objects.filter(project=project, version=str(version_number)).exists():
                version_number += 1
            version = ModelVersion.objects.create(
                project=project,
                source_job=build.source_job,
                source_job_reference=build.source_job_reference
                or (build.source_job.public_id if build.source_job_id else None),
                version=str(version_number),
                requirements_snapshot=build.requirements_snapshot,
                flavor=build.flavor,
                deployability="deployable",
                metrics_summary=metrics_summary or {},
                params_summary=params_summary or {},
                insights_summary=insights_summary or {},
            )
            for asset in build.input_assets.all():
                destination_key = (
                    f"{version_prefix(project.owner.tenant_id, project.public_id, version.public_id)}"
                    f"/artifacts/{asset.kind}/{asset.name}"
                )
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
                        "source_job_id": str(build.source_job.public_id),
                    }
                    if asset.kind == "training_output"
                    else {"artifact_format": build.artifact_format}
                    if asset.kind == "source_artifact"
                    else {},
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
                to_state=version.stage,
                metadata={
                    "source": "training_job" if build.source_job_id else "manual_build",
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
        build.save(update_fields=["version", "image_uri", "image_digest", "status", "error_message", "updated_at"])
        transaction.on_commit(
            lambda: storage.delete_prefix(build_prefix(project.owner.tenant_id, project.public_id, build.public_id))
        )
    return build


def set_alias(*, project, actor, name, version):
    from apps.registry.models import RegistryAlias

    if version.project_id != project.id:
        raise ValidationError({"version": "The version belongs to another project."})
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
