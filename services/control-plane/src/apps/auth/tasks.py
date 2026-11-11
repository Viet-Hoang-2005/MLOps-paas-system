import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, acks_late=True, reject_on_worker_lost=True)
def delete_avatar_object(self, tenant_id, key):
    from apps.auth.services.avatars import cleanup_avatar
    try:
        cleanup_avatar(tenant_id, key)
    except Exception as exc:
        logger.warning("Avatar object cleanup failed; retrying.", exc_info=True)
        raise self.retry(exc=exc, countdown=min(300, 2 ** self.request.retries)) from exc
