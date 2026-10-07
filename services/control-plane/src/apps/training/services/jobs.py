from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.observability.services.lifecycle import record_training_event
from apps.training.models import TrainingJob
from apps.training.services.storage_scope import expected_training_uris, validate_training_uri
from apps.training.tasks import (
    cancel_training_job,
    delete_training_job,
    execute_training_job,
    purge_training_job_outputs,
)
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import training_job_prefix

ACTIVE_STATUSES = {"pending", "queued", "uploading", "running", "cancelling"}


@transaction.atomic
def create_job(*, project, validated_data):
    project = type(project).objects.select_for_update().get(pk=project.pk)
    if project.deletion_state != "active":
        raise Conflict("This project is being deleted.")
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
    try:
        if source_zip:
            storage.put(storage.parse_uri(draft.code_snapshot_uri)[1], source_zip, "application/zip")
        else:
            _snapshot_code(project, draft, storage)

        if training_data:
            if hasattr(training_data, "name") and training_data.name.lower().endswith(".zip"):
                storage.put(storage.parse_uri(draft.data_snapshot_uri)[1], training_data, "application/zip")
            else:
                bundle = BytesIO()
                filename = getattr(training_data, "name", "train.csv") or "train.csv"
                with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
                    archive.writestr(filename, training_data.read())
                storage.put(storage.parse_uri(draft.data_snapshot_uri)[1], bundle.getvalue(), "application/zip")
        else:
            _snapshot_data(project, draft, storage)
    except Exception:
        storage.delete_prefix(training_job_prefix(project.owner.tenant_id, project.public_id, draft.public_id))
        raise
    record_training_event(job=draft, event_type="created", message="Training job created.")
    return draft


def _snapshot_code(project, job, storage):
    assets = list(project.workspace_assets.filter(kind="code"))
    if not assets:
        return
    entry_point_found = any(asset.relative_path == job.entry_point for asset in assets)
    if not entry_point_found:
        raise ValidationError(
            {"entry_point": f"The entry point file '{job.entry_point}' was not found in the workspace code."}
        )
    bundle = BytesIO()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for asset in assets:
            bucket, key = storage.parse_uri(asset.s3_uri)
            body = storage.client.get_object(Bucket=bucket, Key=key)["Body"].read()
            archive.writestr(asset.relative_path, body)
    storage.put(storage.parse_uri(job.code_snapshot_uri)[1], bundle.getvalue(), "application/zip")


def _snapshot_data(project, job, storage):
    assets = list(project.workspace_assets.filter(kind="data"))
    if not assets:
        return
    bundle = BytesIO()
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        for asset in assets:
            bucket, key = storage.parse_uri(asset.s3_uri)
            body = storage.client.get_object(Bucket=bucket, Key=key)["Body"].read()
            archive.writestr(asset.relative_path, body)
    storage.put(storage.parse_uri(job.data_snapshot_uri)[1], bundle.getvalue(), "application/zip")


@transaction.atomic
def retry_job(job, *, storage=None):
    """Retry the original immutable inputs, never the current workspace."""
    project = type(job.project).objects.select_for_update().get(pk=job.project_id)
    job = TrainingJob.objects.select_for_update().get(pk=job.pk)
    if project.deletion_state != "active" or job.deletion_requested_at:
        raise Conflict("This project or job is being deleted.")
    if job.status not in {"failed", "cancelled"}:
        raise Conflict("Only failed or cancelled jobs can be retried.")
    fields = (
        "name",
        "model_flavor",
        "entry_point",
        "requirements_text",
        "vcpu",
        "memory_mb",
        "max_runtime_seconds",
        "accelerator_type",
        "accelerator_count",
        "baseline_version_id",
        "dataset_snapshot_id",
    )
    retry = TrainingJob(
        project=project,
        retry_of=job,
        trigger_kind="retry",
        backend=settings.TRAINING_BACKEND,
        **{field: getattr(job, field) for field in fields},
    )
    storage = storage or S3Storage()
    uris = expected_training_uris(retry, storage.bucket)
    retry.output_uri, retry.mlflow_artifact_uri = uris["output"], uris["mlflow"]
    try:
        for field, kind in (("code_snapshot_uri", "code"), ("data_snapshot_uri", "data")):
            copied = storage.copy(getattr(job, field), storage.parse_uri(uris[kind])[1])
            setattr(retry, field, copied.uri)
        retry.save()
        record_training_event(job=retry, event_type="created", message="Training retry created from immutable inputs.")
        return submit_job(retry)
    except Exception:
        storage.delete_prefix(training_job_prefix(project.owner.tenant_id, project.public_id, retry.public_id))
        raise


@transaction.atomic
def submit_job(job):
    from apps.training.services.resources import validate_resources
    validate_resources({}, job)
    project = type(job.project).objects.select_for_update().get(pk=job.project_id)
    job = TrainingJob.objects.select_for_update().get(pk=job.pk)
    if project.deletion_state != "active":
        raise Conflict("This project is being deleted.")
    if job.deletion_requested_at:
        raise Conflict("This training job is being deleted.")
    if job.status not in {"pending", "failed"}:
        return job
    job.status = "queued"
    job.save(update_fields=["status", "updated_at"])
    transaction.on_commit(lambda: _enqueue(job))
    return job


def _enqueue(job):
    from apps.observability.services.executions import enqueue_safely
    enqueue_safely(job, execute_training_job)


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
        from apps.observability.services.executions import enqueue_safely
        transaction.on_commit(lambda: enqueue_safely(job, cancel_training_job))
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
        if settings.EXECUTION_WATCH_ENABLED:
            job.execution_stop_requested = True
            job.observation_status = "cleanup_pending"
            job.next_execution_check_at = timezone.now()
            task = cancel_training_job
        job.save(
            update_fields=[
                "deletion_requested_at",
                "deletion_error",
                "status",
                "execution_stop_requested",
                "observation_status",
                "next_execution_check_at",
                "updated_at",
            ]
        )
        record_training_event(job=job, event_type=event_type, message=message)
        from apps.observability.services.executions import enqueue_safely
        transaction.on_commit(lambda: enqueue_safely(job, task))
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

