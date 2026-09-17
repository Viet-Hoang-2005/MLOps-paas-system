from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from common.api.exceptions import Conflict
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from infrastructure.storage import S3Storage

from apps.observability.services.lifecycle import record_training_event
from apps.training.models import TrainingJob
from apps.training.services.storage_scope import expected_training_uris, validate_training_uri
from apps.training.tasks import (
    cancel_training_job,
    delete_training_job,
    execute_training_job,
    purge_training_job_outputs,
)

ACTIVE_STATUSES = {"pending", "queued", "uploading", "running", "cancelling"}


def create_job(*, project, validated_data):
    source_zip = validated_data.pop("source_zip", None)
    training_data = validated_data.pop("training_data", None)
    validated_data["backend"] = settings.TRAINING_BACKEND
    public_id = validated_data.pop("public_id", None)
    draft = (
        TrainingJob(public_id=public_id, project=project, **validated_data)
        if public_id
        else TrainingJob(project=project, **validated_data)
    )
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    scoped_uris = expected_training_uris(draft, bucket)
    draft.code_snapshot_uri = scoped_uris["code"]
    draft.data_snapshot_uri = scoped_uris["data"]
    draft.output_uri = scoped_uris["output"]
    draft.mlflow_artifact_uri = scoped_uris["mlflow"]
    draft.save()
    storage = S3Storage()
    if source_zip:
        storage.put(storage.parse_uri(draft.code_snapshot_uri)[1], source_zip, "application/zip")
    else:
        _snapshot_code(project, draft, storage)
    if training_data:
        storage.put(
            storage.parse_uri(draft.data_snapshot_uri)[1],
            training_data,
            training_data.content_type or "text/csv",
        )
    else:
        _snapshot_data(project, draft, storage)
    record_training_event(job=draft, event_type="created", message="Training job created.")
    return draft


def _snapshot_code(project, job, storage):
    assets = list(project.workspace_assets.filter(kind="code"))
    if not assets:
        return
    bundle = BytesIO()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for asset in assets:
            bucket, key = storage.parse_uri(asset.s3_uri)
            body = storage.client.get_object(Bucket=bucket, Key=key)["Body"].read()
            archive.writestr(asset.relative_path, body)
    storage.put(storage.parse_uri(job.code_snapshot_uri)[1], bundle.getvalue(), "application/zip")


def _snapshot_data(project, job, storage):
    asset = project.workspace_assets.filter(kind="data").order_by("-updated_at").first()
    if not asset:
        return
    bucket, key = storage.parse_uri(asset.s3_uri)
    body = storage.client.get_object(Bucket=bucket, Key=key)["Body"].read()
    storage.put(storage.parse_uri(job.data_snapshot_uri)[1], body, asset.content_type or "text/csv")


def submit_job(job):
    if job.deletion_requested_at:
        raise Conflict("This training job is being deleted.")
    if job.status not in {"pending", "failed"}:
        return job
    job.status = "queued"
    job.save(update_fields=["status", "updated_at"])
    transaction.on_commit(lambda: _enqueue(job))
    return job


def _enqueue(job):
    result = execute_training_job.delay(str(job.public_id))
    TrainingJob.objects.filter(pk=job.pk).update(celery_task_id=result.id)


def cancel_job(job):
    with transaction.atomic():
        job = type(job).objects.select_for_update().get(pk=job.pk)
        if job.status in {"completed", "failed", "cancelled"}:
            return job
        job.status = "cancelling"
        job.deletion_error = ""
        job.save(update_fields=["status", "deletion_error", "updated_at"])
        record_training_event(
            job=job,
            event_type="cancellation_requested",
            message="Training cancellation requested.",
        )
        transaction.on_commit(lambda: cancel_training_job.delay(str(job.public_id)))
    return job


def request_job_deletion(job):
    with transaction.atomic():
        job = type(job).objects.select_for_update().get(pk=job.pk)
        if job.builds.filter(status__in=("pending", "queued", "building")).exists():
            raise Conflict("A model build is still using this training output.")

        retrying = bool(job.deletion_requested_at and job.deletion_error)
        if job.deletion_requested_at and not retrying:
            return job

        job.deletion_requested_at = timezone.now()
        job.deletion_error = ""
        if job.status in ACTIVE_STATUSES:
            job.status = "cancelling"
            task = cancel_training_job
            event_type = "delete_cancellation_requested"
            message = "Training deletion requested; runtime cancellation started."
        else:
            task = delete_training_job
            event_type = "deletion_requested"
            message = "Training deletion requested."
        job.save(
            update_fields=[
                "deletion_requested_at",
                "deletion_error",
                "status",
                "updated_at",
            ]
        )
        record_training_event(job=job, event_type=event_type, message=message)
        transaction.on_commit(lambda: task.delay(str(job.public_id)))
    return job


def output_download_url(job):
    if job.outputs_purged_at is not None or not job.outputs.filter(kind="model").exists():
        raise Conflict("Training output is no longer available.")
    storage = S3Storage()
    validate_training_uri(job, storage.bucket, "output", job.output_uri)
    return storage.presigned_get(job.output_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS)


def request_output_purge(job):
    with transaction.atomic():
        job = type(job).objects.select_for_update().get(pk=job.pk)
        if job.outputs_purged_at is not None:
            return job
        if job.status != "completed" or not job.outputs.exists():
            raise Conflict("This training job has no completed output to delete.")
        if job.builds.filter(status__in=("pending", "queued", "building")).exists():
            raise Conflict("Training output is being used by an active model build.")
        job.outputs_purged_at = timezone.now()
        job.save(update_fields=["outputs_purged_at", "updated_at"])
        record_training_event(
            job=job,
            event_type="outputs_purge_requested",
            message="Training output deletion requested.",
        )
        transaction.on_commit(lambda: purge_training_job_outputs.delay(str(job.public_id)))
    return job
