from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.deployment.models import Build, BuildInputAsset
from apps.deployment.tasks import cancel_build, execute_build
from infrastructure.storage import S3Storage
from pathlib import Path
from infrastructure.storage.paths import build_input_prefix, build_prefix


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

        ref_output = job.outputs.filter(kind="reference_data").order_by("-created_at").first()
        if not ref_output or not ref_output.s3_uri:
            raise ValidationError(
                {"job": "This training job has no reference_data output. Training output must include reference data for drift monitoring."}
            )

        build = Build.objects.create(
            project=job.project,
            source_job=job,
            source_job_reference=job.public_id,
            flavor=job.model_flavor,
            artifact_format="raw",
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
                "model",
            )
            destination_key = f"{input_prefix}{filename}"
            stored = storage.copy(output.s3_uri, destination_key)
            BuildInputAsset.objects.create(
                build=build,
                kind="model",
                name=filename,
                s3_uri=stored.uri,
                checksum=stored.checksum or output.checksum,
                size_bytes=stored.size_bytes or output.size_bytes,
                content_type=stored.content_type or output.content_type,
            )

            ref_filename = Path(ref_output.relative_path).name or "reference_data.parquet"
            ref_prefix = build_input_prefix(
                job.project.owner.tenant_id,
                job.project.public_id,
                build.public_id,
                "reference_data",
            )
            ref_destination_key = f"{ref_prefix}{ref_filename}"
            ref_stored = storage.copy(ref_output.s3_uri, ref_destination_key)
            BuildInputAsset.objects.create(
                build=build,
                kind="reference_data",
                name=ref_filename,
                s3_uri=ref_stored.uri,
                checksum=ref_stored.checksum or ref_output.checksum,
                size_bytes=ref_stored.size_bytes or ref_output.size_bytes,
                content_type=ref_stored.content_type or ref_output.content_type,
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
