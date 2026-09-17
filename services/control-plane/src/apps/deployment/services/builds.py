from pathlib import Path

from django.db import transaction
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_input_prefix, build_prefix
from rest_framework.exceptions import ValidationError

from apps.deployment.models import Build, BuildInputAsset
from apps.deployment.tasks import cancel_build, execute_build

BUILD_FILE_FIELDS = {
    "source_artifact": "source_artifact",
    "label_mapping_file": "label_mapping",
    "metrics_file": "metrics",
    "params_file": "params",
    "model_insights_file": "model_insights",
    "feature_importance_file": "feature_importance",
    "input_schema_file": "input_schema",
}


def request_build(version, backend):
    if version.deployability not in {"deployable", "unknown"}:
        raise ValidationError({"version": version.deployability_reason or "This version is not deployable."})
    source = version.artifacts.filter(kind__in=("source", "training_output")).first()
    if not source:
        raise ValidationError({"version": "This version has no buildable source artifact."})
    build = Build.objects.create(
        project=version.project,
        version=version,
        flavor=version.flavor,
        artifact_format=source.metadata.get("artifact_format", "raw"),
        requirements_snapshot=version.requirements_snapshot,
        backend=backend,
        status="queued",
    )
    transaction.on_commit(lambda: _enqueue(build))
    return build


import uuid


def create_build_presigned_url(*, project, validated_data, storage=None):
    storage = storage or S3Storage()
    filename = Path(validated_data["filename"]).name
    content_type = validated_data.get("content_type") or "application/octet-stream"
    draft_id = uuid.uuid4()
    input_prefix = build_input_prefix(
        project.owner.tenant_id,
        project.public_id,
        draft_id,
        "source_artifact",
    )
    key = f"{input_prefix}{filename}"
    s3_uri = f"s3://{storage.bucket}/{key}"
    upload_url = storage.presigned_put(s3_uri, expires_in=1800, content_type=content_type)
    return {
        "upload_url": upload_url,
        "s3_uri": s3_uri,
        "key": key,
        "filename": filename,
        "draft_build_id": str(draft_id),
        "expires_in": 1800,
    }


def request_manual_build(*, project, validated_data, backend, storage=None):
    storage = storage or S3Storage()
    data = dict(validated_data)
    source_artifact_uri = data.pop("source_artifact_uri", "")
    source_artifact_name = data.pop("source_artifact_name", "")
    source_artifact_size = data.pop("source_artifact_size", None)
    source_artifact_checksum = data.pop("source_artifact_checksum", "")
    files = {field: data.pop(field, None) for field in BUILD_FILE_FIELDS}
    build = None
    try:
        with transaction.atomic():
            build = Build.objects.create(
                project=project,
                flavor=data["flavor"],
                artifact_format=data.get("artifact_format", "raw"),
                requirements_snapshot=data.get("requirements_text", ""),
                backend=backend,
                status="pending",
            )
            # 1. Handle source artifact (either uploaded file or direct S3 URI)
            if files.get("source_artifact"):
                uploaded = files.pop("source_artifact")
                filename = Path(uploaded.name).name
                input_prefix = build_input_prefix(
                    project.owner.tenant_id,
                    project.public_id,
                    build.public_id,
                    "source_artifact",
                )
                key = f"{input_prefix}{filename}"
                stored = storage.put(key, uploaded, uploaded.content_type or "application/octet-stream")
                BuildInputAsset.objects.create(
                    build=build,
                    kind="source_artifact",
                    name=filename,
                    s3_uri=stored.uri,
                    checksum=stored.checksum,
                    size_bytes=stored.size_bytes,
                    content_type=stored.content_type,
                )
            elif source_artifact_uri:
                bucket, key = storage.parse_uri(source_artifact_uri)
                if bucket != storage.bucket:
                    raise ValidationError({"source_artifact_uri": "Source artifact must belong to storage bucket."})
                expected_scope = f"users/{project.owner.tenant_id}/models/{project.public_id}/"
                if not key.startswith(expected_scope):
                    raise ValidationError({"source_artifact_uri": "Cross-tenant or cross-project artifact access prohibited."})

                actual_size = source_artifact_size or 0
                actual_checksum = source_artifact_checksum or ""
                actual_content_type = "application/octet-stream"
                try:
                    head_resp = storage.client.head_object(Bucket=bucket, Key=key)
                    actual_size = head_resp.get("ContentLength", actual_size)
                    actual_content_type = head_resp.get("ContentType", actual_content_type)
                    actual_checksum = head_resp.get("Metadata", {}).get("sha256", actual_checksum)
                except Exception:
                    pass

                filename = source_artifact_name or Path(key).name
                BuildInputAsset.objects.create(
                    build=build,
                    kind="source_artifact",
                    name=filename,
                    s3_uri=source_artifact_uri,
                    checksum=actual_checksum,
                    size_bytes=actual_size,
                    content_type=actual_content_type,
                )

            # 2. Handle any remaining auxiliary files (metrics, params, label_mapping, etc.)
            for field, kind in BUILD_FILE_FIELDS.items():
                if field == "source_artifact":
                    continue
                uploaded = files.get(field)
                if uploaded is None:
                    continue
                filename = Path(uploaded.name).name
                input_prefix = build_input_prefix(
                    project.owner.tenant_id,
                    project.public_id,
                    build.public_id,
                    kind,
                )
                key = f"{input_prefix}{filename}"
                stored = storage.put(key, uploaded, uploaded.content_type or "application/octet-stream")
                BuildInputAsset.objects.create(
                    build=build,
                    kind=kind,
                    name=filename,
                    s3_uri=stored.uri,
                    checksum=stored.checksum,
                    size_bytes=stored.size_bytes,
                    content_type=stored.content_type,
                )

            build.status = "queued"
            build.save(update_fields=["status", "updated_at"])
            transaction.on_commit(lambda: _enqueue(build))
    except Exception:
        if build is not None:
            storage.delete_prefix(build_prefix(project.owner.tenant_id, project.public_id, build.public_id))
        raise
    return build


def request_training_build(*, job, backend, storage=None):
    """Create or reuse the image build backed by one immutable training output."""

    storage = storage or S3Storage()
    with transaction.atomic():
        job = type(job).objects.select_for_update().select_related("project", "project__owner").get(pk=job.pk)
        if job.status != "completed":
            raise ValidationError({"job": "Training must complete successfully before it can be registered."})
        if job.outputs_purged_at is not None:
            raise ValidationError({"job": "Training outputs have been deleted."})
        existing = job.builds.filter(status__in=("pending", "queued", "building", "ready")).first()
        if existing:
            return existing, False
        output = job.outputs.filter(kind="model").order_by("-created_at").first()
        if not output or not output.s3_uri:
            raise ValidationError({"job": "This training job has no model output."})

        build = Build.objects.create(
            project=job.project,
            source_job=job,
            source_job_reference=job.public_id,
            flavor=job.model_flavor,
            artifact_format="training_output",
            requirements_snapshot=job.requirements_text,
            backend=backend,
            status="pending",
        )
        try:
            filename = Path(output.relative_path).name or "model.tar.gz"
            input_prefix = build_input_prefix(
                job.project.owner.tenant_id,
                job.project.public_id,
                build.public_id,
                "training_output",
            )
            destination_key = f"{input_prefix}{filename}"
            stored = storage.copy(output.s3_uri, destination_key)
            BuildInputAsset.objects.create(
                build=build,
                kind="training_output",
                name=filename,
                s3_uri=stored.uri,
                checksum=stored.checksum or output.checksum,
                size_bytes=stored.size_bytes or output.size_bytes,
                content_type=stored.content_type or output.content_type,
            )
        except Exception:
            storage.delete_prefix(build_prefix(job.project.owner.tenant_id, job.project.public_id, build.public_id))
            raise
        build.status = "queued"
        build.save(update_fields=["status", "updated_at"])
        transaction.on_commit(lambda: _enqueue(build))
        return build, True


def _enqueue(build):
    result = execute_build.delay(str(build.public_id))
    Build.objects.filter(pk=build.pk).update(celery_task_id=result.id)


def request_cancel(build):
    if build.status in {"ready", "failed", "cancelled"}:
        return build
    build.status = "cancelled"
    build.save(update_fields=["status", "updated_at"])
    transaction.on_commit(lambda: cancel_build.delay(str(build.public_id)))
    return build
