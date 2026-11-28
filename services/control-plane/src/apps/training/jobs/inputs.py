from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.training.jobs.capabilities import capability_for_token
from apps.training.jobs.models import TrainingJob
from apps.training.jobs.storage_scope import validate_training_uri
from infrastructure.storage import S3Storage


def input_download_urls(job_id, token):
    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().get(public_id=job_id)
        capability = capability_for_token(job=job, purpose="input_download", token=token)
        if (
            not capability
            or capability.consumed_at
            or job.status not in {"queued", "running"}
            or job.execution_stop_requested
            or job.deletion_requested_at
            or (job.project_id and job.project.deletion_state != "active")
        ):
            raise PermissionDenied("Invalid input download capability.")
        capability.consumed_at = timezone.now()
        capability.save(update_fields=["consumed_at"])
    storage = S3Storage()
    validate_training_uri(job, storage.bucket, "code", job.code_snapshot_uri)
    data_url = ""
    if job.input_contract != "workspace":
        validate_training_uri(job, storage.bucket, "data", job.data_snapshot_uri)
        data_url = storage.presigned_get(job.data_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS)
    return {
        "source_url": storage.presigned_get(job.code_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS),
        "data_url": data_url,
    }
