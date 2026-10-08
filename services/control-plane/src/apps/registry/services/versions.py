from contextlib import contextmanager

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.observability.services.lifecycle import record_registry_event
from apps.observability.services.outbox import enqueue_event
from apps.registry.models import ModelArtifact, ModelMetric, ModelVersion
from common.validation.artifacts import MAX_REFERENCE_DATA_BYTES
from infrastructure.execution.image_references import repository_from_reference
from infrastructure.execution.image_registry import image_registry_for
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
    with _registration_storage(storage) as storage, transaction.atomic():
        project = type(build.project).objects.select_for_update().get(pk=build.project_id)
        build = type(build).objects.select_for_update().select_related("project", "project__owner").get(pk=build.pk)
        if build.status != "ready" or project.deletion_state != "active" or build.deletion_state != "active":
            raise ValidationError({"build": "Only successful builds of active projects can be registered."})
        if build.version_id:
            return build
        metrics_summary = metrics_summary if metrics_summary is not None else build.metrics_summary
        params_summary = params_summary if params_summary is not None else build.params_summary
        insights_summary = insights_summary if insights_summary is not None else build.insights_summary
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
                        "source_job_id": str(build.source_job_reference),
                    }
                    if asset.kind == "training_output"
                    else {"artifact_format": build.artifact_format}
                    if asset.kind == "source_artifact"
                    else asset.metadata,
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
        build.registration_status = "registered"
        build.registration_error = ""
        build.save(
            update_fields=[
                "version",
                "image_uri",
                "image_digest",
                "status",
                "error_message",
                "registration_status",
                "registration_error",
                "updated_at",
            ]
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


def add_supplemental_artifacts(
    *,
    version,
    actor,
    source_code_file=None,
    reference_data_file=None,
    label_mapping_file=None,
    input_schema_file=None,
    metrics_file=None,
    params_file=None,
    model_insights_file=None,
    feature_importance_file=None,
    storage=None,
):
    import json
    from django.utils import timezone
    from common.api.exceptions import Conflict
    from common.validation.artifacts import (
        validate_reference_data_file,
        validate_source_code_file,
    )
    from apps.catalog.services.snapshots import parse_label_mapping_payload

    if (
        not source_code_file
        and not reference_data_file
        and not label_mapping_file
        and not input_schema_file
        and not metrics_file
        and not params_file
        and not model_insights_file
        and not feature_importance_file
    ):
        raise ValidationError({"artifacts": "No supplemental artifact provided."})

    storage = storage or S3Storage()
    uploaded_uris = []
    try:
        with transaction.atomic():
            project = type(version.project).objects.select_for_update().get(pk=version.project_id)
            if getattr(project, "deletion_state", "active") != "active":
                raise Conflict("This project is being deleted.")
            version = ModelVersion.objects.select_for_update().get(pk=version.pk)

            prefix = version_prefix(project.owner.tenant_id, project.public_id, version.public_id)

            if source_code_file:
                if version.artifacts.filter(kind="source_code").exists():
                    raise Conflict("This version already has a source code artifact and cannot be replaced.")
                filename = validate_source_code_file(source_code_file)
                key = f"{prefix}/artifacts/supplemental/source/{filename}"
                stored = storage.put(key, source_code_file, "text/x-python")
                uploaded_uris.append(stored.uri)
                ModelArtifact.objects.create(
                    version=version,
                    kind="source_code",
                    name=filename,
                    uri=stored.uri,
                    checksum=stored.checksum,
                    size_bytes=stored.size_bytes,
                    content_type="text/x-python",
                    metadata={
                        "provenance": "supplemental_upload",
                        "uploaded_by": getattr(actor, "email", "system"),
                        "uploaded_at": timezone.now().isoformat(),
                    },
                )
                record_registry_event(
                    version=version,
                    actor=actor,
                    event_type="artifact_added",
                    message=f"Added supplemental source code {filename}",
                    metadata={"kind": "source_code", "name": filename},
                )

            if reference_data_file:
                if version.artifacts.filter(kind="reference_data").exists():
                    raise Conflict("This version already has a reference data artifact and cannot be replaced.")
                filename, _ = validate_reference_data_file(reference_data_file)
                content_type = "text/csv"
                key = f"{prefix}/artifacts/supplemental/reference/{filename}"
                stored = storage.put(key, reference_data_file, content_type)
                uploaded_uris.append(stored.uri)
                ModelArtifact.objects.create(
                    version=version,
                    kind="reference_data",
                    name=filename,
                    uri=stored.uri,
                    checksum=stored.checksum,
                    size_bytes=stored.size_bytes,
                    content_type=content_type,
                    metadata={
                        "provenance": "supplemental_upload",
                        "format": "csv",
                        "uploaded_by": getattr(actor, "email", "system"),
                        "uploaded_at": timezone.now().isoformat(),
                    },
                )
                record_registry_event(
                    version=version,
                    actor=actor,
                    event_type="artifact_added",
                    message=f"Added supplemental reference data {filename}",
                    metadata={"kind": "reference_data", "name": filename, "format": "csv"},
                )

            attribute_uploads = [
                ("label_mapping", label_mapping_file, "application/json"),
                ("input_schema", input_schema_file, "application/json"),
                ("metrics", metrics_file, "application/json"),
                ("params", params_file, "application/json"),
                ("model_insights", model_insights_file, "application/json"),
                ("feature_importance", feature_importance_file, "application/json"),
            ]

            for kind, f_obj, default_ct in attribute_uploads:
                if not f_obj:
                    continue
                if version.artifacts.filter(kind=kind).exists():
                    raise Conflict(f"This version already has a {kind} artifact and cannot be replaced.")
                filename = getattr(f_obj, "name", f"{kind}.json")
                if not filename.lower().endswith(".json"):
                    raise ValidationError({kind: f"{kind} must be a .json file."})

                try:
                    raw_bytes = f_obj.read(4 * 1024 * 1024 + 1)
                    if len(raw_bytes) > 4 * 1024 * 1024:
                        raise ValueError("JSON file exceeds 4 MiB.")
                    if kind == "label_mapping":
                        raw_content = parse_label_mapping_payload(filename, raw_bytes)
                    else:
                        raw_content = json.loads(raw_bytes.decode("utf-8"))
                    if kind in {"metrics", "params", "model_insights", "input_schema"} and not isinstance(raw_content, dict):
                        raise ValueError("Expected a JSON object.")
                    if kind == "feature_importance" and not isinstance(raw_content, (dict, list)):
                        raise ValueError("Expected a JSON object or array.")
                except (UnicodeDecodeError, ValueError) as exc:
                    raise ValidationError({kind: "Upload a valid JSON file under 4 MiB."}) from exc
                finally:
                    f_obj.seek(0)

                original = {
                    "metrics": version.metrics_summary,
                    "params": version.params_summary,
                    "model_insights": version.insights_summary,
                    "feature_importance": version.insights_summary,
                }.get(kind) or {}
                if kind in {"metrics", "params", "model_insights", "feature_importance"} and isinstance(raw_content, dict):
                    overlap = set(raw_content) & set(original)
                    if overlap:
                        raise ValidationError({kind: f"Keys already exist in the registered snapshot: {', '.join(sorted(overlap))}."})

                key = f"{prefix}/artifacts/supplemental/{kind}/{filename}"
                stored = storage.put(key, f_obj, default_ct)
                uploaded_uris.append(stored.uri)
                ModelArtifact.objects.create(
                    version=version,
                    kind=kind,
                    name=filename,
                    uri=stored.uri,
                    checksum=stored.checksum,
                    size_bytes=stored.size_bytes,
                    content_type=default_ct,
                    metadata={
                        "provenance": "supplemental_upload",
                        "uploaded_by": getattr(actor, "email", "system"),
                        "uploaded_at": timezone.now().isoformat(),
                        "summary": raw_content,
                    },
                )
                record_registry_event(
                    version=version,
                    actor=actor,
                    event_type="artifact_added",
                    message=f"Added supplemental {kind} {filename}",
                    metadata={"kind": kind, "name": filename},
                )

    except Exception:
        for uri in uploaded_uris:
            try:
                storage.delete(uri)
            except Exception:
                pass
        raise

    return version


def get_version_reference_preview(version, storage=None) -> dict:
    from common.validation.artifacts import parse_reference_preview

    storage = storage or S3Storage()
    artifact = version.artifacts.filter(kind="reference_data").first()
    if not artifact or not artifact.uri:
        raise ValidationError({"reference_data": "This version does not have a reference dataset."})
    try:
        raw = storage.read(artifact.uri, max_bytes=MAX_REFERENCE_DATA_BYTES)
    except Exception as exc:
        raise ValidationError({"reference_data": "Could not read reference data from storage."}) from exc

    return parse_reference_preview(raw, artifact.name, max_rows=100)
