import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


def _on_post_migrate(sender, **kwargs):
    from apps.auth.services.bootstrap import ensure_admin_account

    try:
        ensure_admin_account()
    except Exception as exc:
        logger.warning("Failed to auto-init admin account on post_migrate: %s", exc)


class AuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auth"
    label = "identity"

    def ready(self):
        post_migrate.connect(_on_post_migrate, sender=self)
