"""Restartable copy/verify before deleting a legacy Project storage namespace."""

from django.db import transaction

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob, TrainingStorageCopy
from apps.training.services.storage_scope import training_prefix_for
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import tenant_training_job_prefix


def _replace(value, source, destination):
    if isinstance(value, str):
        return destination + value[len(source) :] if value.startswith(source) else value
    if isinstance(value, list):
        return [_replace(item, source, destination) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, source, destination) for key, item in value.items()}
    return value


def migrate_job_storage(job, *, storage=None):
    if job.storage_layout == "tenant":
        return job
    if job.status not in {"completed", "failed", "cancelled"}:
        raise Conflict("Stop training before migrating storage.")
    if not job.project_id or job.project.deletion_state != "deleting":
        raise Conflict("Legacy storage migration requires a deleting Project.")
    storage = storage or S3Storage()
    source_key = training_prefix_for(job) + "/"
    destination_key = tenant_training_job_prefix(job.owner.tenant_id, job.public_id) + "/"
    source = f"s3://{storage.bucket}/{source_key}"
    destination = f"s3://{storage.bucket}/{destination_key}"
    outputs = list(job.outputs.values_list("s3_uri", flat=True))
    pointers = {
        field: getattr(job, field)
        for field in ("code_snapshot_uri", "data_snapshot_uri", "output_uri", "mlflow_artifact_uri")
    }
    if any(uri and not uri.startswith(source) for uri in [*pointers.values(), *outputs]):
        raise Conflict("A training object is outside its original storage scope; deletion is blocked.")
    listed = set()
    paginator = storage.client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=storage.bucket, Prefix=source_key):
        for item in page.get("Contents", []):
            key = item["Key"]
            if not key.startswith(source_key):
                raise Conflict("Unexpected storage listing scope.")
            uri = f"s3://{storage.bucket}/{key}"
            target = destination_key + key[len(source_key) :]
            target_uri = f"s3://{storage.bucket}/{target}"
            head = storage.head(uri)
            checkpoint = TrainingStorageCopy.objects.filter(job=job, source_uri=uri, source_etag=head.etag).first()
            if checkpoint:
                try:
                    if storage.compute_sha256(target_uri) == checkpoint.checksum:
                        listed.add(uri)
                        continue
                except Exception:
                    pass
            checksum = storage.compute_sha256(uri)
            storage.copy(
                uri,
                target,
                checksum=checksum,
                size_bytes=head.size_bytes,
                content_type=head.content_type,
                expected_etag=head.etag,
            )
            if storage.head(uri).etag != head.etag or storage.compute_sha256(target_uri) != checksum:
                raise Conflict("Training object verification failed; source objects were retained.")
            TrainingStorageCopy.objects.update_or_create(
                job=job,
                source_uri=uri,
                defaults={"destination_uri": target_uri, "source_etag": head.etag, "checksum": checksum},
            )
            listed.add(uri)
    if any(uri and uri not in listed for uri in outputs):
        raise Conflict("A recorded training artifact is missing; Project deletion is blocked.")
    with transaction.atomic():
        project = ModelProject.objects.select_for_update().get(pk=job.project_id)
        current = TrainingJob.objects.select_for_update().get(pk=job.pk)
        if current.storage_layout == "tenant":
            return current
        if (
            project.deletion_state != "deleting"
            or current.output_revision != job.output_revision
            or current.status not in {"completed", "failed", "cancelled"}
        ):
            raise Conflict("Training changed during storage migration.")
        for field, original in pointers.items():
            if getattr(current, field) != original:
                raise Conflict("Training storage changed during migration.")
            setattr(current, field, _replace(original, source, destination))
        for output in current.outputs.select_for_update():
            output.s3_uri = _replace(output.s3_uri, source, destination)
            output.save(update_fields=["s3_uri"])
        current.tracking = _replace(current.tracking, source, destination)
        current.storage_layout = "tenant"
        current.save(update_fields=[*pointers, "storage_layout", "tracking", "updated_at"])
    return current


def migrate_project_storage(project):
    for job in project.training_jobs.exclude(storage_layout="tenant").select_related("owner", "project"):
        migrate_job_storage(job)
