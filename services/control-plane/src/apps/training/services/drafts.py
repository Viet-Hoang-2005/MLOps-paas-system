"""A job owns one editable input and admits at most one execution."""

import uuid
from datetime import timedelta
from io import BytesIO
from zipfile import ZipFile

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.training.models import TrainingJob, TrainingJobEntry, TrainingJobSecret
from apps.training.services import workspaces
from apps.training.services.storage_scope import expected_training_uris, training_prefix_for
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage

TERMINAL = {"completed", "failed", "cancelled"}
CONFIG_FIELDS = (
    "model_flavor",
    "entry_point",
    "vcpu",
    "memory_mb",
    "max_runtime_seconds",
    "accelerator_type",
    "accelerator_count",
    "accelerator_model",
    "local_gpu_id",
)
PREPARATION_LEASE = timedelta(minutes=10)


def create_draft(*, owner, values=None):
    from apps.observability.services.lifecycle import record_training_event

    with transaction.atomic():
        job = TrainingJob.objects.create(owner=owner, storage_layout="tenant", backend=settings.TRAINING_BACKEND)
        changes = {key: value for key, value in (values or {}).items() if key != "revision"}
        if changes:
            job = workspaces.update_workspace(job, revision=job.revision, changes=changes)
        record_training_event(job=job, event_type="created", message="Training draft created.")
    return job


def recover_preparations():
    """Fence abandoned snapshot writers. No runtime has been admitted for these rows."""
    return TrainingJob.objects.filter(
        status="pending",
        submitted_at__isnull=True,
        preparation_started_at__lt=timezone.now() - PREPARATION_LEASE,
        deletion_requested_at__isnull=True,
    ).update(
        status="editing",
        submission_token=None,
        preparation_started_at=None,
        run_key=None,
        error_message="Preparation interrupted. Run again.",
    )


def submit_draft(job, *, revision, run_key, storage=None):
    from apps.training.services.jobs import _submit_job_atomic
    from apps.training.services.resources import validate_resources

    with transaction.atomic():
        locked = TrainingJob.objects.select_for_update().get(pk=job.pk)
        if locked.deletion_requested_at:
            raise Conflict("This training job is being deleted.")
        if locked.run_key == run_key:
            if locked.submitted_at or (
                locked.status == "pending"
                and locked.preparation_started_at
                and locked.preparation_started_at > timezone.now() - PREPARATION_LEASE
            ):
                return locked
        elif locked.submitted_at or locked.status != "editing":
            raise Conflict("This job already has a submission.")
        # An expired preparation may only be reclaimed while it has no admitted runtime.
        if locked.status == "pending" and not locked.submitted_at:
            if locked.preparation_started_at and locked.preparation_started_at > timezone.now() - PREPARATION_LEASE:
                raise Conflict("Input is being prepared.")
            locked.status = "editing"
            locked.save(update_fields=["status"])
        workspaces._lock(locked, revision)
        if any(getattr(locked, field) is None for field in ("vcpu", "memory_mb", "max_runtime_seconds")):
            raise ValidationError("Select CPU, memory and maximum runtime before running.")
        token = uuid.uuid4()
        locked.run_key = run_key
        locked.submission_token = token
        locked.preparation_started_at = timezone.now()
        locked.status = "pending"
        locked.error_message = ""
        try:
            with transaction.atomic():
                locked.save(
                    update_fields=[
                        "run_key",
                        "submission_token",
                        "preparation_started_at",
                        "status",
                        "error_message",
                        "updated_at",
                    ]
                )
        except IntegrityError as exc:
            raise Conflict("This submission key is unavailable.") from exc
    job = locked
    staged = False
    try:
        storage = storage or S3Storage()
        uris = expected_training_uris(job, storage.bucket)
        capacity = None
        if settings.TRAINING_BACKEND == "docker":
            from apps.training.services.local_resources import require_capacity

            capacity = require_capacity(force=True)
        validate_resources({}, job, local_capacity=capacity)
        verified_gpu_id = ""
        if job.accelerator_type == "gpu" and job.backend == "docker":
            from apps.training.services.local_gpu import require_device

            require_device(job.local_gpu_id)
            verified_gpu_id = job.local_gpu_id
        snapshot = workspaces.snapshot_input(job, revision=revision, storage=storage, preparing=True)
        with ZipFile(BytesIO(snapshot["archive"])) as archive:
            requirements = (
                archive.read("requirements.txt").decode("utf-8") if "requirements.txt" in archive.namelist() else ""
            )
        staged = True
        storage.put(storage.parse_uri(uris["code"])[1], snapshot["archive"], "application/zip")
        empty = BytesIO()
        with ZipFile(empty, "w"):
            pass
        storage.put(storage.parse_uri(uris["data"])[1], empty.getvalue(), "application/zip")
        with transaction.atomic():
            if job.backend == "argo":
                from apps.training.services.quota import lock_owner

                lock_owner(job.owner_id)
            current = TrainingJob.objects.select_for_update().get(pk=job.pk)
            if (
                current.status != "pending"
                or current.submission_token != token
                or current.revision != revision
                or current.deletion_requested_at
                or current.submitted_at
            ):
                raise Conflict("The preparation is no longer current.")
            current.environment_snapshot = dict(current.environment)
            current.secret_snapshot = {
                secret.name: bytes(secret.ciphertext).decode("ascii") for secret in current.secrets.all()
            }
            current.input_revision = revision
            current.requirements_text = requirements
            current.code_snapshot_uri, current.data_snapshot_uri = uris["code"], uris["data"]
            current.output_uri, current.mlflow_artifact_uri = uris["output"], uris["mlflow"]
            current.save()
            return _submit_job_atomic(current, verified_gpu_id=verified_gpu_id, local_capacity=capacity)
    except Exception:
        # An on_commit broker failure must never undo an accepted submission.
        with transaction.atomic():
            current = TrainingJob.objects.select_for_update().filter(pk=job.pk).first()
            accepted = current is not None and current.submitted_at is not None
            if current and not accepted and current.submission_token == token and not current.deletion_requested_at:
                current.status = "editing"
                current.run_key = current.submission_token = None
                current.preparation_started_at = None
                current.save(
                    update_fields=["status", "run_key", "submission_token", "preparation_started_at", "updated_at"]
                )
        if not accepted and staged:
            storage.delete_prefix(f"{training_prefix_for(job)}/input/submissions/{token}/")
        raise


def clone_draft(source, *, creation_key, retry=False, storage=None):
    """Clone frozen Input, and only Secrets that still exist at commit time."""
    existing = TrainingJob.objects.filter(creation_key=creation_key).first()
    if existing:
        relation = existing.retry_of_id if retry else existing.cloned_from_id
        if existing.owner_id != source.owner_id or relation != source.pk:
            raise Conflict("This creation key is unavailable.")
        return existing
    if source.status not in ({"failed", "cancelled"} if retry else TERMINAL) or source.deletion_requested_at:
        raise Conflict("Only finished jobs can be copied.")
    storage = storage or S3Storage()
    draft = TrainingJob(
        owner=source.owner,
        storage_layout="tenant",
        backend=settings.TRAINING_BACKEND,
        creation_key=creation_key,
        environment=dict(source.environment_snapshot),
        **{field: getattr(source, field) for field in CONFIG_FIELDS},
    )
    if retry:
        draft.retry_of, draft.trigger_kind = source, "retry"
    else:
        draft.cloned_from = source
    from .snapshots import input_snapshot

    entries = input_snapshot(source, storage=storage)["entries"]
    if not any(item["path"] == source.entry_point and item["kind"] == "script" for item in entries):
        raise Conflict("The source Input is missing its Python entry point.")
    archive_bytes = storage.read(source.code_snapshot_uri, max_bytes=workspaces.MAX_WORKSPACE_SNAPSHOT)
    staged = []
    try:
        with ZipFile(BytesIO(archive_bytes)) as archive:
            for item in entries:
                entry = TrainingJobEntry(relative_path=item["path"], kind=item["kind"])
                if item["kind"] != "folder":
                    payload = archive.read(item["path"])
                    workspaces.validate_file(item["path"], item["kind"], payload)
                    stored = storage.put(
                        f"{training_prefix_for(draft)}/draft/objects/{uuid.uuid4().hex}",
                        payload,
                        "text/csv" if item["kind"] == "data" else "text/plain; charset=utf-8",
                    )
                    entry.s3_uri, entry.checksum = stored.uri, stored.checksum
                    entry.size_bytes, entry.content_type = stored.size_bytes, stored.content_type
                staged.append(entry)
        with transaction.atomic():
            source = TrainingJob.objects.select_for_update().get(pk=source.pk)
            if source.status not in TERMINAL or source.deletion_requested_at:
                raise Conflict("The source job is being deleted.")
            secrets = list(source.secrets.select_for_update())
            draft.save()
            for entry in staged:
                entry.job = draft
            TrainingJobEntry.objects.bulk_create(staged)
            TrainingJobSecret.objects.bulk_create(
                [
                    TrainingJobSecret(job=draft, name=secret.name, ciphertext=bytes(secret.ciphertext))
                    for secret in secrets
                ]
            )
        return draft
    except Exception:
        if not TrainingJob.objects.filter(public_id=draft.public_id).exists():
            storage.delete_prefix(training_prefix_for(draft) + "/")
        existing = TrainingJob.objects.filter(creation_key=creation_key, owner=source.owner).first()
        if existing and (existing.retry_of_id if retry else existing.cloned_from_id) == source.pk:
            return existing
        raise
