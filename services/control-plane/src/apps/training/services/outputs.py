import json
from pathlib import Path
from typing import Any
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.observability.services.lifecycle import record_training_event
from apps.training.models import TrainingJob, TrainingOutput
from common.api.exceptions import Conflict
from common.validation.artifacts import (
    MAX_REFERENCE_DATA_BYTES,
    parse_reference_preview,
    validate_reference_data_file,
    validate_source_code_file,
)
from common.validation.revisions import validate_output_revision
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import training_output_prefix


def verify_training_output(job, storage=None):
    from botocore.config import Config
    from .storage_scope import validate_training_uri

    storage = storage or S3Storage(client_config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 0}))
    validate_training_uri(job, storage.bucket, "output", job.output_uri)
    bucket, key = storage.parse_uri(job.output_uri)
    if not storage.client.head_object(Bucket=bucket, Key=key).get("ContentLength"):
        raise ValueError("Training output is empty.")


def serialize_output_asset(output: TrainingOutput, storage=None) -> dict[str, Any]:
    content = None
    if output.kind == "source_code" and output.s3_uri:
        storage = storage or S3Storage()
        try:
            content = storage.read(output.s3_uri, max_bytes=5 * 1024 * 1024).decode("utf-8", errors="replace")
        except Exception:
            content = None

    return {
        "id": str(output.public_id),
        "name": Path(output.relative_path).name,
        "relative_path": output.relative_path,
        "kind": output.kind,
        "checksum": output.checksum or "",
        "size_bytes": output.size_bytes or 0,
        "content_type": output.content_type or "",
        "metadata": output.metadata or {},
        "created_at": output.created_at.isoformat() if output.created_at else "",
        "content": content,
    }


def get_model_output_summary(job: TrainingJob, storage=None) -> dict[str, Any]:
    storage = storage or S3Storage()

    metrics = {}
    params = {}
    insights = {}
    for m_out in job.outputs.filter(kind__in=("metric", "insight")):
        if not m_out.s3_uri:
            continue
        try:
            raw = storage.read(m_out.s3_uri)
            val = json.loads(raw.decode("utf-8"))
            if m_out.kind == "metric" and isinstance(val, dict):
                metrics.update(val)
            elif m_out.kind == "insight" and "param" in m_out.relative_path.lower() and isinstance(val, dict):
                params.update(val)
            elif m_out.kind == "insight":
                if isinstance(val, dict):
                    insights.update(val)
                elif isinstance(val, list):
                    insights[Path(m_out.relative_path).stem] = val
        except Exception:
            pass

    if isinstance(job.tracking, dict):
        if "metrics" in job.tracking and isinstance(job.tracking["metrics"], dict):
            metrics = {**job.tracking["metrics"], **metrics}
        if "params" in job.tracking and isinstance(job.tracking["params"], dict):
            params = {**job.tracking["params"], **params}
        if "insights" in job.tracking and isinstance(job.tracking["insights"], dict):
            insights = {**job.tracking["insights"], **insights}

    model_artifact = job.outputs.filter(kind="model").first()
    source_code = job.outputs.filter(kind="source_code").first()
    reference_data = job.outputs.filter(kind="reference_data").first()

    can_edit = (
        job.status == "completed"
        and not job.outputs_purged_at
        and getattr(job.project, "deletion_state", "active") == "active"
    )
    can_build = can_edit and (model_artifact is not None)

    return {
        "job_id": str(job.public_id),
        "project_id": str(job.project.public_id),
        "output_revision": job.output_revision,
        "model_flavor": job.model_flavor,
        "entry_point": job.entry_point or "train.py",
        "requirements_text": job.requirements_text or "",
        "model_artifact": serialize_output_asset(model_artifact, storage) if model_artifact else None,
        "source_code": serialize_output_asset(source_code, storage) if source_code else None,
        "reference_data": serialize_output_asset(reference_data, storage) if reference_data else None,
        "metrics": metrics,
        "params": params,
        "insights": insights,
        "can_edit": can_edit,
        "can_build": can_build,
        "outputs_purged_at": job.outputs_purged_at.isoformat() if job.outputs_purged_at else None,
    }


def mutate_training_output(*, job: TrainingJob, user, data: dict[str, Any], storage=None) -> dict[str, Any]:
    storage = storage or S3Storage()
    new_uploaded_uris: list[str] = []
    old_uris_to_delete: list[str] = []

    try:
        with transaction.atomic():
            project = type(job.project).objects.select_for_update().get(pk=job.project_id)
            if getattr(project, "deletion_state", "active") != "active":
                raise Conflict("This project is being deleted.")
            job = TrainingJob.objects.select_for_update().get(pk=job.pk)
            if job.status != "completed":
                raise Conflict("Cannot edit output of a job that is not completed.")
            if job.outputs_purged_at:
                raise Conflict("Outputs for this training job have been purged.")

            expected_revision = validate_output_revision(data.get("output_revision"))
            if expected_revision != job.output_revision:
                raise Conflict("Revision conflict. Please reload latest outputs before saving.")

            remove_assets = data.get("remove_assets") or []
            if isinstance(remove_assets, str):
                try:
                    remove_assets = json.loads(remove_assets)
                except Exception:
                    remove_assets = [remove_assets]
            remove_assets_set = set(remove_assets)

            source_code_file = data.get("source_code_file")
            reference_data_file = data.get("reference_data_file")

            # Removals
            if "source_code" in remove_assets_set and not source_code_file:
                old_source = job.outputs.filter(kind="source_code").first()
                if old_source:
                    if old_source.s3_uri:
                        old_uris_to_delete.append(old_source.s3_uri)
                    old_source.delete()

            if "reference_data" in remove_assets_set and not reference_data_file:
                old_ref = job.outputs.filter(kind="reference_data").first()
                if old_ref:
                    if old_ref.s3_uri:
                        old_uris_to_delete.append(old_ref.s3_uri)
                    old_ref.delete()

            tenant_id = project.owner.tenant_id
            project_id = project.public_id
            job_id = job.public_id
            out_prefix = training_output_prefix(tenant_id, project_id, job_id)

            # Source code mutation
            if source_code_file:
                filename = validate_source_code_file(source_code_file)
                key = f"{out_prefix}supplemental/source/{uuid.uuid4().hex[:8]}_{filename}"
                stored = storage.put(key, source_code_file, "text/x-python")
                new_uploaded_uris.append(stored.uri)

                old_source = job.outputs.filter(kind="source_code").first()
                if old_source:
                    if old_source.s3_uri:
                        old_uris_to_delete.append(old_source.s3_uri)
                    old_source.delete()

                TrainingOutput.objects.create(
                    job=job,
                    kind="source_code",
                    relative_path=filename,
                    s3_uri=stored.uri,
                    checksum=stored.checksum,
                    size_bytes=stored.size_bytes,
                    content_type="text/x-python",
                    metadata={
                        "updated_by": getattr(user, "username", getattr(user, "email", "system")),
                        "updated_at": timezone.now().isoformat(),
                    },
                )

            # Reference data mutation
            if reference_data_file:
                filename, _ = validate_reference_data_file(reference_data_file)
                content_type = "text/csv"
                key = f"{out_prefix}supplemental/reference/{uuid.uuid4().hex[:8]}_{filename}"
                stored = storage.put(key, reference_data_file, content_type)
                new_uploaded_uris.append(stored.uri)

                old_ref = job.outputs.filter(kind="reference_data").first()
                if old_ref:
                    if old_ref.s3_uri:
                        old_uris_to_delete.append(old_ref.s3_uri)
                    old_ref.delete()

                TrainingOutput.objects.create(
                    job=job,
                    kind="reference_data",
                    relative_path=filename,
                    s3_uri=stored.uri,
                    checksum=stored.checksum,
                    size_bytes=stored.size_bytes,
                    content_type=content_type,
                    metadata={
                        "format": "csv",
                        "updated_by": getattr(user, "username", getattr(user, "email", "system")),
                        "updated_at": timezone.now().isoformat(),
                    },
                )

            job.output_revision += 1
            job.save(update_fields=["output_revision", "updated_at"])

            record_training_event(
                job=job,
                event_type="output_mutated",
                message=f"Training outputs updated to Revision #{job.output_revision}",
                metadata={"output_revision": job.output_revision},
            )

            def cleanup_old_objects():
                for uri in old_uris_to_delete:
                    try:
                        storage.delete(uri)
                    except Exception:
                        pass

            transaction.on_commit(cleanup_old_objects)
    except Exception:
        for uri in new_uploaded_uris:
            try:
                storage.delete(uri)
            except Exception:
                pass
        raise

    return get_model_output_summary(job, storage=storage)


def get_job_reference_preview(job: TrainingJob, storage=None) -> dict[str, Any]:
    storage = storage or S3Storage()
    ref_output = job.outputs.filter(kind="reference_data").first()
    if not ref_output or not ref_output.s3_uri:
        raise ValidationError({"reference_data": "This training job does not have a reference dataset."})
    try:
        raw = storage.read(ref_output.s3_uri, max_bytes=MAX_REFERENCE_DATA_BYTES)
    except Exception as exc:
        raise ValidationError({"reference_data": "Could not read reference data from storage."}) from exc

    return parse_reference_preview(raw, ref_output.relative_path, max_rows=100)
