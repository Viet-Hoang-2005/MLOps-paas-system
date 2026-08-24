import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.training.models import TrainingJobCapability


def issue_capability(job, purpose, *, ttl_seconds=None):
    """Create a short-lived, opaque capability without persisting its raw value."""
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(
        seconds=ttl_seconds if ttl_seconds is not None else _ttl_seconds(job)
    )
    TrainingJobCapability.objects.filter(job=job, purpose=purpose, consumed_at__isnull=True).delete()
    TrainingJobCapability.objects.create(
        job=job,
        purpose=purpose,
        token_hash=_token_hash(token),
        expires_at=expires_at,
    )
    return token


def capability_for_token(*, job, purpose, token):
    if not token:
        return None
    return (
        TrainingJobCapability.objects.filter(
            job=job,
            purpose=purpose,
            token_hash=_token_hash(token),
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )


def _ttl_seconds(job):
    requested = int(job.max_runtime_seconds) + settings.TRAINING_CAPABILITY_GRACE_SECONDS
    return min(
        max(requested, settings.TRAINING_PRESIGNED_URL_TTL_SECONDS),
        settings.TRAINING_CAPABILITY_MAX_TTL_SECONDS,
    )


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
