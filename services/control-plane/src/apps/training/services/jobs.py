from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings
from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.observability.services.lifecycle import record_training_event
from apps.training.models import TrainingJob
from apps.training.services.storage_scope import expected_training_uris, training_prefix_for, validate_training_uri
from apps.training.tasks import (
    cancel_training_job,
    delete_training_job,
    execute_training_job,
    purge_training_job_outputs,
)
from common.api.exceptions import Conflict, ServiceUnavailable
from infrastructure.storage import S3Storage

ACTIVE_STATUSES = {"pending", "queued", "uploading", "running", "cancelling"}


def _discard_unused_inputs(storage, project, job):
    """Remove staged inputs of a job that was never saved.

    A failure can also surface after the commit (an on_commit callback that cannot reach the
    broker); the inputs then belong to a real job and must stay.
    """
    if not TrainingJob.objects.filter(public_id=job.public_id).exists():
        storage.delete_prefix(training_prefix_for(job) + "/")


def _require_active_project(project):
    """Lock the project row and refuse work for one that is being deleted."""
    project = type(project).objects.select_for_update(of=("self",)).select_related("owner").get(pk=project.pk)
    if project.deletion_state != "active":
        raise Conflict("This project is being deleted.")
    return project


def create_job(*, project, validated_data):
    """Stage a job's inputs, then create it.

    Writing the code and data snapshots is object-storage I/O, so it runs with no lock held.
    The job row is created afterwards in a short transaction that checks the project again;
    until then only unreferenced objects exist, and they are removed if anything fails.
    """
    if settings.TRAINING_BACKEND == "docker" and validated_data.get("accelerator_type") == "gpu":
        from apps.training.services.local_gpu import require_device
        require_device(validated_data.get("local_gpu_id", ""))
    with transaction.atomic():
        project = _require_active_project(project)
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
        with transaction.atomic():
            _require_active_project(project)
            draft.save()
            record_training_event(job=draft, event_type="created", message="Training job created.")
    except Exception:
        _discard_unused_inputs(storage, project, draft)
        raise
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


RETRY_FIELDS = (
    "model_flavor",
    "entry_point",
    "requirements_text",
    "vcpu",
    "memory_mb",
    "max_runtime_seconds",
    "accelerator_type",
    "accelerator_count",
    "accelerator_model",
    "local_gpu_id",
    "baseline_version_id",
    "dataset_snapshot_id",
)


def _check_retryable(project, job):
    if (project and project.deletion_state != "active") or job.deletion_requested_at:
        raise Conflict("This project or job is being deleted.")
    if job.status not in {"failed", "cancelled"}:
        raise Conflict("Only failed or cancelled jobs can be retried.")


def retry_job(job, *, storage=None):
    """Retry the original immutable inputs, never the current workspace.

    The inputs are copied with no lock held; the retry is created in a second short
    transaction that checks the original job and project again.
    """
    with transaction.atomic():
        from apps.catalog.models import ModelProject
        project = ModelProject.objects.select_for_update(of=("self",)).select_related("owner").get(pk=job.project_id) if job.project_id else None
        job = TrainingJob.objects.select_for_update().get(pk=job.pk)
        _check_retryable(project, job)
        retry = TrainingJob(
            project=project,
            owner=job.owner,
            workspace=job.workspace,
            input_contract=job.input_contract,
            storage_layout=job.storage_layout if project else "tenant",
            workspace_revision=job.workspace_revision,
            environment_snapshot=job.environment_snapshot,
            retry_of=job,
            trigger_kind="retry",
            backend=settings.TRAINING_BACKEND,
            **{field: getattr(job, field) for field in RETRY_FIELDS},
        )
        sources = {"code_snapshot_uri": job.code_snapshot_uri, "data_snapshot_uri": job.data_snapshot_uri}
        if job.secret_snapshot:
            if not job.workspace_id:
                raise Conflict("The workspace secrets are no longer available; create a new run.")
            secrets = list(job.workspace.secrets.filter(name__in=job.secret_snapshot))
            if {secret.name for secret in secrets} != set(job.secret_snapshot):
                raise Conflict("A required secret was deleted; create a new run.")
            retry.secret_snapshot = {secret.name: bytes(secret.ciphertext).decode("ascii") for secret in secrets}
    from apps.training.services.resources import validate_resources
    local_capacity = None
    if retry.backend == "docker":
        from apps.training.services.local_resources import require_capacity
        local_capacity = require_capacity(force=True)
    validate_resources({}, retry, local_capacity=local_capacity)
    if settings.TRAINING_BACKEND == "docker" and retry.accelerator_type == "gpu":
        from apps.training.services.local_gpu import require_device
        require_device(retry.local_gpu_id)
    storage = storage or S3Storage()
    uris = expected_training_uris(retry, storage.bucket)
    retry.output_uri, retry.mlflow_artifact_uri = uris["output"], uris["mlflow"]
    try:
        for field, kind in (("code_snapshot_uri", "code"), ("data_snapshot_uri", "data")):
            copied = storage.copy(sources[field], storage.parse_uri(uris[kind])[1])
            setattr(retry, field, copied.uri)
        with transaction.atomic():
            # Workspace mutations/deletion share this lock. Recheck after the
            # potentially slow storage copy so a deleted secret cannot be
            # reissued from the earlier validation snapshot.
            if job.secret_snapshot:
                from apps.training.models import TrainingWorkspace
                workspace = TrainingWorkspace.objects.select_for_update().filter(
                    pk=job.workspace_id, owner_id=job.owner_id,
                ).first()
                if workspace is None:
                    raise Conflict("The workspace secrets are no longer available; create a new run.")
                secrets = list(workspace.secrets.filter(name__in=job.secret_snapshot))
                if {secret.name for secret in secrets} != set(job.secret_snapshot):
                    raise Conflict("A required secret was deleted; create a new run.")
                retry.secret_snapshot = {secret.name: bytes(secret.ciphertext).decode("ascii") for secret in secrets}
            if retry.backend == "argo":
                from apps.training.services.quota import lock_owner
                lock_owner(job.owner_id)
            project = type(project).objects.select_for_update(of=("self",)).select_related("owner").get(pk=project.pk) if project else None
            _check_retryable(project, TrainingJob.objects.select_for_update().get(pk=job.pk))
            retry.save()
            record_training_event(
                job=retry, event_type="created", message="Training retry created from immutable inputs."
            )
            return submit_job(retry, verify_gpu=False, local_capacity=local_capacity)
    except Exception:
        _discard_unused_inputs(storage, project, retry)
        raise


def submit_job(job, *, verify_gpu=True, local_capacity=None):
    from apps.training.services.resources import validate_resources
    if job.backend == "docker" and local_capacity is None:
        from apps.training.services.local_resources import require_capacity
        local_capacity = require_capacity(force=True)
    validate_resources({}, job, local_capacity=local_capacity)
    if verify_gpu and settings.TRAINING_BACKEND == "docker" and job.accelerator_type == "gpu":
        from apps.training.services.local_gpu import require_device
        require_device(job.local_gpu_id)
    verified_gpu_id = job.local_gpu_id if job.accelerator_type == "gpu" and settings.TRAINING_BACKEND == "docker" else ""
    try:
        return _submit_job_atomic(job, verified_gpu_id=verified_gpu_id, local_capacity=local_capacity)
    except DatabaseError as exc:
        raise ServiceUnavailable("Training quota is temporarily unavailable.") from exc


@transaction.atomic
def _submit_job_atomic(job, *, verified_gpu_id, local_capacity=None):
    if job.backend == "argo":
        from apps.training.services.quota import lock_owner
        lock_owner(job.owner_id)
    from apps.catalog.models import ModelProject
    project = ModelProject.objects.select_for_update().filter(pk=job.project_id).first() if job.project_id else None
    job = TrainingJob.objects.select_for_update().get(pk=job.pk)
    from apps.training.services.resources import validate_resources
    validate_resources({}, job, local_capacity=local_capacity)
    if settings.TRAINING_BACKEND == "docker" and job.accelerator_type == "gpu" and job.local_gpu_id != verified_gpu_id:
        raise Conflict("The selected GPU changed; retry the request.")
    if project and project.deletion_state != "active":
        raise Conflict("This project is being deleted.")
    if job.deletion_requested_at:
        raise Conflict("This training job is being deleted.")
    if job.status != "pending":
        raise Conflict("Only pending jobs can be submitted.")
    if job.backend == "argo":
        from apps.training.services.quota import reserve
        reserve(job)
    elif job.backend == "docker":
        from apps.training.services.local_resources import reserve
        reserve(job, local_capacity)
    job.status = "queued"
    job.save(update_fields=["status", "dispatch_deadline_at", "updated_at"])
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
        job.capabilities.filter(purpose="tracking").delete()
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
        job.capabilities.filter(purpose="tracking").delete()
        if job.status in ACTIVE_STATUSES:
            job.status = "cancelling"
            task = cancel_training_job
            event_type = "delete_cancellation_requested"
            message = "Training deletion requested; runtime cancellation started."
        else:
            task = delete_training_job
            event_type = "deletion_requested"
            message = "Training deletion requested."
        if settings.TRAINING_EXECUTION_WATCH_ENABLED:
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

