"""Build requests.

Copying a model's inputs into the build's own prefix is slow object-storage I/O. It never
runs while a row or project lock is held: the request is validated under the lock and a plain
snapshot is taken, the inputs are copied with no lock, and the build is created in a second
short transaction that validates again. The Build row does not exist before its inputs do,
so a crash between the steps leaves only unreferenced objects, never a half-built Build.
"""

import json
import uuid
from dataclasses import dataclass, field
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

ACTIVE_BUILD_STATUSES = ("pending", "queued", "building")
PREVIEW_SUMMARY_FIELDS = {
    "metrics": "metrics_summary",
    "params": "params_summary",
    "model_insights": "insights_summary",
    "feature_importance": "insights_summary",
}


@dataclass
class _Source:
    """One object to copy into the build's input prefix, captured while the lock was held."""

    kind: str
    name: str
    uri: str
    checksum: str = ""
    size_bytes: int | None = None
    content_type: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class _Staged:
    source: _Source
    copied: object


def _enqueue(build):
    result = execute_build.delay(str(build.public_id))
    Build.objects.filter(pk=build.pk).update(celery_task_id=result.id)


def _discard(storage, tenant_id, project_public_id, build_public_id):
    storage.delete_prefix(build_prefix(tenant_id, project_public_id, build_public_id))


def _discard_unused(storage, tenant_id, project_public_id, build_public_id):
    """Remove the copied inputs of a build that was never created.

    A failure can also surface after the commit (an on_commit callback that cannot reach the
    broker); the inputs then belong to a real Build and must stay.
    """
    if not Build.objects.filter(public_id=build_public_id).exists():
        _discard(storage, tenant_id, project_public_id, build_public_id)


def _asset_from_copy(build, staged):
    source, copied = staged.source, staged.copied
    return BuildInputAsset(
        build=build,
        kind=source.kind,
        name=source.name,
        s3_uri=copied.uri,
        checksum=copied.checksum or source.checksum,
        size_bytes=copied.size_bytes or source.size_bytes,
        content_type=copied.content_type or source.content_type,
        metadata=source.metadata,
    )


def request_training_build(*, job, backend, output_revision=None, storage=None):
    """Create or reuse the image build backed by immutable training outputs."""

    storage = storage or S3Storage()
    expected_revision = validate_output_revision(output_revision, required=False)

    # 1. Validate and snapshot under the lock.
    with transaction.atomic():
        project = type(job.project).objects.select_for_update().get(pk=job.project_id)
        if project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        job = type(job).objects.select_for_update().select_related("project", "project__owner").get(pk=job.pk)
        _check_training_job(job, expected_revision)
        existing = _existing_training_build(job)
        if existing:
            return existing, False
        output = job.outputs.filter(kind="model").order_by("-created_at").first()
        if not output or not output.s3_uri:
            raise ValidationError({"job": "This training job has no model output."})
        sources = [
            _Source(
                kind="training_output",
                name=Path(output.relative_path).name or "model.tar.gz",
                uri=output.s3_uri,
                checksum=output.checksum,
                size_bytes=output.size_bytes,
                content_type=output.content_type,
                metadata={"source_job_id": str(job.public_id)},
            )
        ]
        for supp in job.outputs.filter(kind__in=("source_code", "reference_data")):
            if supp.s3_uri:
                sources.append(
                    _Source(
                        kind=supp.kind,
                        name=Path(supp.relative_path).name,
                        uri=supp.s3_uri,
                        checksum=supp.checksum,
                        size_bytes=supp.size_bytes,
                        content_type=supp.content_type,
                        metadata={"entry_point": job.entry_point} if supp.kind == "source_code" else supp.metadata,
                    )
                )
        summary_sources = [
            (m_out.kind, m_out.relative_path, m_out.s3_uri)
            for m_out in job.outputs.filter(kind__in=("metric", "insight"))
            if m_out.s3_uri
        ]
        revision = job.output_revision
        tenant_id, project_public_id = job.project.owner.tenant_id, job.project.public_id
        flavor, requirements = job.model_flavor, job.requirements_text
    build_public_id = uuid.uuid4()

    # 2. Copy with no lock held.
    try:
        staged = [
            _Staged(
                source,
                storage.copy(
                    source.uri,
                    f"{build_input_prefix(tenant_id, project_public_id, build_public_id, source.kind)}{source.name}",
                ),
            )
            for source in sources
        ]
        summaries = _training_summaries(storage, summary_sources)

        # 3. Create the Build in a short transaction, validating again.
        with transaction.atomic():
            project = type(job.project).objects.select_for_update().get(pk=job.project_id)
            if project.deletion_state != "active":
                raise Conflict("This project is being deleted.")
            job = type(job).objects.select_for_update().select_related("project", "project__owner").get(pk=job.pk)
            _check_training_job(job, expected_revision)
            if job.output_revision != revision:
                raise Conflict("Training output changed while the build was being prepared. Try again.")
            existing = _existing_training_build(job)
            if existing:
                # A concurrent request won; its build is the one to use.
                _discard(storage, tenant_id, project_public_id, build_public_id)
                return existing, False
            build = Build.objects.create(
                public_id=build_public_id,
                project=job.project,
                source_job=job,
                source_job_reference=job.public_id,
                flavor=flavor,
                artifact_format="training_output",
                requirements_snapshot=requirements,
                source_output_revision=revision,
                backend=backend,
                status="queued",
                **summaries,
            )
            BuildInputAsset.objects.bulk_create(_asset_from_copy(build, item) for item in staged)
            transaction.on_commit(lambda: _enqueue(build))
            return build, True
    except Exception:
        _discard_unused(storage, tenant_id, project_public_id, build_public_id)
        raise


def _check_training_job(job, expected_revision):
    if job.status != "completed":
        raise ValidationError({"job": "Training must complete successfully before it can be registered."})
    if job.outputs_purged_at is not None:
        raise ValidationError({"job": "Training outputs have been deleted."})
    if expected_revision is not None and expected_revision != job.output_revision:
        raise Conflict("Training output changed in another session. Reload before building.")


def _existing_training_build(job):
    existing = job.builds.filter(status__in=ACTIVE_BUILD_STATUSES).first()
    if not existing:
        return None
    if existing.deletion_state != "active":
        raise Conflict("Wait for the previous training build cleanup to finish.")
    if existing.source_output_revision == job.output_revision:
        return existing
    raise Conflict("A build for this training job with a different revision is already running.")


def _training_summaries(storage, summary_sources):
    metrics, params, insights = {}, {}, {}
    for kind, relative_path, uri in summary_sources:
        try:
            value = json.loads(storage.read(uri).decode("utf-8"))
        except Exception:
            continue
        if kind == "metric" and isinstance(value, dict):
            metrics.update(value)
        elif kind == "insight" and "param" in relative_path.lower() and isinstance(value, dict):
            params.update(value)
        elif kind == "insight":
            if isinstance(value, dict):
                insights.update(value)
            elif isinstance(value, list):
                insights[Path(relative_path).stem] = value
    return {"metrics_summary": metrics, "params_summary": params, "insights_summary": insights}


def request_preview_build(*, project, revision, backend, storage=None):
    storage = storage or S3Storage()

    # 1. Validate and snapshot under the lock.
    with transaction.atomic():
        project = type(project).objects.select_for_update().get(pk=project.pk)
        preview = _check_preview(project, revision)
        sources = [
            _Source(kind=asset.kind, name=asset.name, uri=asset.s3_uri)
            for asset in preview.assets.all()
        ]
        flavor, artifact_format, requirements = preview.flavor, preview.artifact_format, preview.requirements_text
        tenant_id, project_public_id = project.owner.tenant_id, project.public_id
    build_public_id = uuid.uuid4()

    # 2. Copy and read with no lock held.
    try:
        staged = [
            _Staged(
                source,
                storage.copy(
                    source.uri,
                    f"{build_input_prefix(tenant_id, project_public_id, build_public_id, source.kind)}{source.name}",
                ),
            )
            for source in sources
        ]
        summaries = _preview_summaries(storage, staged)

        # 3. Create the Build in a short transaction, validating again.
        with transaction.atomic():
            project = type(project).objects.select_for_update().get(pk=project.pk)
            _check_preview(project, revision)
            build = Build.objects.create(
                public_id=build_public_id,
                project=project,
                preview_revision=revision,
                flavor=flavor,
                artifact_format=artifact_format,
                requirements_snapshot=requirements,
                backend=backend,
                status="queued",
                **summaries,
            )
            BuildInputAsset.objects.bulk_create(_asset_from_copy(build, item) for item in staged)
            transaction.on_commit(lambda: _enqueue(build))
        return build
    except Exception:
        _discard_unused(storage, tenant_id, project_public_id, build_public_id)
        raise


def _check_preview(project, revision):
    if project.deletion_state != "active":
        raise Conflict("This project is being deleted.")
    preview = ModelPreview.objects.select_for_update().get(project=project)
    if preview.revision != revision:
        raise Conflict("Preview changed. Reload before building.")
    if not preview.flavor or not preview.assets.filter(kind="source_artifact").exists():
        raise ValidationError({"preview": "Upload a valid model artifact before building."})
    return preview


def _preview_summaries(storage, staged):
    summaries = {"metrics_summary": {}, "params_summary": {}, "insights_summary": {}}
    for item in staged:
        field_name = PREVIEW_SUMMARY_FIELDS.get(item.source.kind)
        if not field_name:
            continue
        value = json.loads(storage.read(item.copied.uri))
        if isinstance(value, list) and item.source.kind == "feature_importance":
            value = {"kind": "feature_importance", "items": value}
        if isinstance(value, dict):
            summaries[field_name] = {**summaries[field_name], **value}
    return summaries


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
    # Only the checks need the lock. The new request validates again, so the inputs are copied
    # with no lock held.
    with transaction.atomic():
        project = type(build.project).objects.select_for_update().get(pk=build.project_id)
        build = Build.objects.select_for_update().select_related("source_job").get(pk=build.pk)
        if build.deletion_state != "active" or project.deletion_state != "active":
            raise Conflict("This build or project is being deleted.")
        if build.status not in {"ready", "failed", "cancelled"} or build.registration_status == "registering":
            raise Conflict("Wait for this build and registration to finish before rebuilding.")
        from_job = bool(build.source_job_reference or build.source_job_id)
        if from_job and not build.source_job_id:
            raise Conflict("The original training job has been deleted. Choose a new build source.")
        source_job = build.source_job if from_job else None
        revision = None if from_job else project.preview.revision
    if from_job:
        result, _ = request_training_build(job=source_job, backend=backend, storage=storage)
        return result
    return request_preview_build(project=project, revision=revision, backend=backend, storage=storage)


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
