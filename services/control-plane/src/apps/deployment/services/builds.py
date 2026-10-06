import json
from pathlib import Path

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ModelPreview
from apps.deployment.models import Build, BuildInputAsset
from apps.deployment.tasks import cancel_build, execute_build
from common.api.exceptions import Conflict
from common.validation.revisions import validate_output_revision
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_input_prefix, build_prefix


def request_training_build(*, job, backend, output_revision=None, storage=None):
    """Create or reuse the image build backed by immutable training outputs."""

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
        expected_revision = validate_output_revision(output_revision, required=False)
        if expected_revision is not None and expected_revision != job.output_revision:
            raise Conflict("Training output changed in another session. Reload before building.")

        existing = job.builds.filter(status__in=("pending", "queued", "building")).first()
        if existing:
            if existing.deletion_state != "active":
                raise Conflict("Wait for the previous training build cleanup to finish.")
            if existing.source_output_revision == job.output_revision:
                return existing, False
            raise Conflict("A build for this training job with a different revision is already running.")

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
            source_output_revision=job.output_revision,
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
            for supp in job.outputs.filter(kind__in=("source_code", "reference_data")):
                if not supp.s3_uri:
                    continue
                name = Path(supp.relative_path).name
                copied = storage.copy(
                    supp.s3_uri,
                    f"{build_input_prefix(job.project.owner.tenant_id, job.project.public_id, build.public_id, supp.kind)}{name}",
                )
                BuildInputAsset.objects.create(
                    build=build,
                    kind=supp.kind,
                    name=name,
                    s3_uri=copied.uri,
                    checksum=copied.checksum or supp.checksum,
                    size_bytes=copied.size_bytes or supp.size_bytes,
                    content_type=copied.content_type or supp.content_type,
                    metadata={"entry_point": job.entry_point} if supp.kind == "source_code" else supp.metadata,
                )

            for m_out in job.outputs.filter(kind__in=("metric", "insight")):
                if not m_out.s3_uri:
                    continue
                try:
                    content = storage.read(m_out.s3_uri).decode("utf-8")
                    val = json.loads(content)
                    if m_out.kind == "metric" and isinstance(val, dict):
                        build.metrics_summary = {**build.metrics_summary, **val}
                    elif m_out.kind == "insight" and "param" in m_out.relative_path.lower() and isinstance(val, dict):
                        build.params_summary = {**build.params_summary, **val}
                    elif m_out.kind == "insight":
                        if isinstance(val, dict):
                            build.insights_summary = {**build.insights_summary, **val}
                        elif isinstance(val, list):
                            build.insights_summary = {**build.insights_summary, Path(m_out.relative_path).stem: val}
                except Exception:
                    pass
            build.save(update_fields=["metrics_summary", "params_summary", "insights_summary"])
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


def request_rebuild(build, *, backend, storage=None):
    """Start a new attempt from the current Preview or the original training output."""
    with transaction.atomic():
        project = type(build.project).objects.select_for_update().get(pk=build.project_id)
        build = Build.objects.select_for_update().get(pk=build.pk)
        if build.deletion_state != "active" or project.deletion_state != "active":
            raise Conflict("This build or project is being deleted.")
        if build.status not in {"ready", "failed", "cancelled"} or build.registration_status == "registering":
            raise Conflict("Wait for this build and registration to finish before rebuilding.")
        if build.source_job_reference or build.source_job_id:
            if not build.source_job_id:
                raise Conflict("The original training job has been deleted. Choose a new build source.")
            result, _ = request_training_build(job=build.source_job, backend=backend, storage=storage)
            return result
        return request_preview_build(
            project=project, revision=project.preview.revision, backend=backend, storage=storage
        )


def request_build_deletion(build):
    from apps.deployment.tasks import delete_build

    with transaction.atomic():
        project = type(build.project).objects.select_for_update().get(pk=build.project_id)
        build = Build.objects.select_for_update().get(pk=build.pk)
        if project.deletion_state != "active":
            raise Conflict("This project is already being deleted.")
        if build.version_id or build.registration_status in {"registered", "registering"} or build.deployments.exists():
            raise Conflict("A registered or registering build cannot be deleted from build history.")
        if build.deletion_state == "deleting":
            return build
        build.deletion_state = "deleting"
        build.deletion_error = ""
        build.save(update_fields=["deletion_state", "deletion_error", "updated_at"])
        transaction.on_commit(lambda: delete_build.delay(str(build.public_id)))
    return build
