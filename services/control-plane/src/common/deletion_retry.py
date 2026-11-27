from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def deletion_cleanup_retry_at(now=None):
    return (now or timezone.now()) + timedelta(seconds=max(1, settings.DELETION_RECONCILE_GRACE_SECONDS))
