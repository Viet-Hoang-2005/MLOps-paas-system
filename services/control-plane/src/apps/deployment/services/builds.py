from pathlib import Path
import json

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.deployment.models import Build, BuildInputAsset
from apps.catalog.models import ModelPreview
from common.api.exceptions import Conflict
from apps.deployment.tasks import cancel_build, execute_build
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_input_prefix, build_prefix


def request_training_build(*, job, backend, storage=None):
    """Create or reuse the image build backed by one immutable training output."""

    storage = storage or S3Storage()
    with transaction.atomic():
        project = type(job.project).objects.select_for_update().get(pk=job.project_id)
        if project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        job = type(job).objects.select_for_update().select_related("project", "project__owner").get(pk=job.pk)
        if job.status != "completed":
            raise ValidationError({"job": "Training must complete successfully before it can be registered."})
        if job.outputs_purged_at is not None:
            raise ValidationError({"job": "Training outputs have been deleted."})
        existing = job.builds.filter(status__in=("pending", "queued", "building")).first()
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
            preview_revision=job.project.preview.revision,
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
                metadata={"source_job_id": str(job.public_id)},
            )
            for kind, uri in (("source_code", job.code_snapshot_uri), ("reference_data", job.reference_snapshot_uri)):
                if not uri:
                    continue
                name = Path(uri).name
                copied = storage.copy(
                    uri,
                    f"{build_input_prefix(job.project.owner.tenant_id, job.project.public_id, build.public_id, kind)}{name}",
                )
                BuildInputAsset.objects.create(
                    build=build,
                    kind=kind,
                    name=name,
                    s3_uri=copied.uri,
                    checksum=copied.checksum,
                    size_bytes=copied.size_bytes,
                    content_type=copied.content_type,
                    metadata={"entry_point": job.entry_point} if kind == "source_code" else {},
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


def request_preview_build(*, project, revision, backend, storage=None):
    storage = storage or S3Storage()
    with transaction.atomic():
        project = type(project).objects.select_for_update().get(pk=project.pk)
        if project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        preview = ModelPreview.objects.select_for_update().get(project=project)
        if preview.revision != revision:
            raise Conflict("Preview changed. Reload before building.")
        if not preview.flavor or not preview.assets.filter(kind="source_artifact").exists():
            raise ValidationError({"preview": "Upload a valid model artifact before building."})
        build = Build.objects.create(
            project=project,
            preview_revision=revision,
            flavor=preview.flavor,
            artifact_format=preview.artifact_format,
            requirements_snapshot=preview.requirements_text,
            backend=backend,
            status="queued",
        )
        try:
            for asset in preview.assets.all():
                copied = storage.copy(
                    asset.s3_uri,
                    f"{build_input_prefix(project.owner.tenant_id, project.public_id, build.public_id, asset.kind)}{asset.name}",
                )
                BuildInputAsset.objects.create(
                    build=build,
                    kind=asset.kind,
                    name=asset.name,
                    s3_uri=copied.uri,
                    checksum=copied.checksum,
                    size_bytes=copied.size_bytes,
                    content_type=copied.content_type,
                )
                if asset.kind in {"metrics", "params", "model_insights", "feature_importance"}:
                    value = json.loads(storage.read(copied.uri))
                    field = {
                        "metrics": "metrics_summary",
                        "params": "params_summary",
                        "model_insights": "insights_summary",
                        "feature_importance": "insights_summary",
                    }[asset.kind]
                    if isinstance(value, list) and asset.kind == "feature_importance":
                        value = {"kind": "feature_importance", "items": value}
                    if isinstance(value, dict):
                        setattr(build, field, {**getattr(build, field), **value})
            build.save(update_fields=["metrics_summary", "params_summary", "insights_summary"])
        except Exception:
            storage.delete_prefix(build_prefix(project.owner.tenant_id, project.public_id, build.public_id))
            raise
        transaction.on_commit(lambda: _enqueue(build))
    return build


def request_cancel(build):
    with transaction.atomic():
        type(build.project).objects.select_for_update().get(pk=build.project_id)
        build = Build.objects.select_for_update().get(pk=build.pk)
        if build.status in {"ready", "failed", "cancelled"}:
            return build
        build.status = "cancelled"
        build.save(update_fields=["status", "updated_at"])
        transaction.on_commit(lambda: cancel_build.delay(str(build.public_id)))
    return build
