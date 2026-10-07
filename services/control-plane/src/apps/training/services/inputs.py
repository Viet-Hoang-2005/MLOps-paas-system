from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.training.models import TrainingJob
from apps.training.services.capabilities import capability_for_token
from infrastructure.storage import S3Storage
from .storage_scope import validate_training_uri


def input_download_urls(job_id, token):
    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().get(public_id=job_id)
        capability = capability_for_token(job=job, purpose="input_download", token=token)
        if not capability or capability.consumed_at or job.status not in {"queued", "running"} or job.execution_stop_requested or job.deletion_requested_at or job.project.deletion_state != "active":
            raise PermissionDenied("Invalid input download capability.")
        capability.consumed_at = timezone.now()
        capability.save(update_fields=["consumed_at"])
    storage = S3Storage()
    validate_training_uri(job, storage.bucket, "code", job.code_snapshot_uri)
    validate_training_uri(job, storage.bucket, "data", job.data_snapshot_uri)
    return {
        "source_url": storage.presigned_get(job.code_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS),
        "data_url": storage.presigned_get(job.data_snapshot_uri, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS),
    }
