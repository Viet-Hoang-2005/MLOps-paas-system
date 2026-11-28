import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, acks_late=True, reject_on_worker_lost=True)
def delete_avatar_object(self, tenant_id, key):
    from apps.auth.account.avatars import cleanup_avatar

    try:
        cleanup_avatar(tenant_id, key)
    except Exception as exc:
        logger.warning("Avatar object cleanup failed; retrying.", exc_info=True)
        raise self.retry(exc=exc, countdown=min(300, 2**self.request.retries)) from exc


@shared_task(bind=True, max_retries=3, acks_late=True, reject_on_worker_lost=True)
def stop_user_active_executions(self, user_id):
    from apps.auth.account.lifecycle import stop_user_active_runtimes

    try:
        return stop_user_active_runtimes(user_id)
    except Exception as exc:
        logger.warning("Stopping active runtimes failed for user %s; retrying.", user_id, exc_info=True)
        raise self.retry(exc=exc, countdown=min(300, 2**self.request.retries)) from exc


@shared_task(bind=True, max_retries=2, acks_late=True, reject_on_worker_lost=True)
def purge_expired_deleted_accounts(self):
    from apps.auth.account.lifecycle import purge_expired_deleted_accounts_batch

    try:
        return purge_expired_deleted_accounts_batch()
    except Exception as exc:
        logger.warning("Expired deleted accounts purge batch failed; retrying.", exc_info=True)
        raise self.retry(exc=exc, countdown=min(300, 2**self.request.retries)) from exc
