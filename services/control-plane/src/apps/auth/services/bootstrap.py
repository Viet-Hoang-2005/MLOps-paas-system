import logging
from typing import Optional, Tuple

from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


def ensure_admin_account(
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[Optional[object], bool]:
    """
    Ensure the administrator account exists with staff and superuser permissions.

    If email is not provided, reads from settings.ADMIN_EMAIL (or BOOTSTRAP_ADMIN_EMAIL).
    If password is not provided, reads from settings.ADMIN_PASSWORD (or BOOTSTRAP_ADMIN_PASSWORD).

    Returns:
        (user, created): Tuple where user is the CustomUser instance (or None if skipped)
        and created is a boolean indicating whether a new account was created.
    """
    admin_email = (email if email is not None else getattr(settings, "ADMIN_EMAIL", "")).strip()
    admin_password = password if password is not None else getattr(settings, "ADMIN_PASSWORD", "")

    if not admin_email:
        logger.info("ADMIN_EMAIL is empty; skipping administrator bootstrap.")
        return None, False

    if admin_password and len(admin_password) < 8:
        logger.warning(
            "ADMIN_PASSWORD must contain at least 8 characters; skipping administrator bootstrap."
        )
        return None, False

    User = get_user_model()
    user, created = User.objects.get_or_create(
        email=admin_email,
        defaults={
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
            "full_name": "Administrator",
        },
    )

    if created:
        if admin_password:
            user.set_password(admin_password)
        else:
            user.set_unusable_password()
        user.save()
        logger.info("Created administrator account: %s", admin_email)
    else:
        logger.info("Account already exists; bootstrap left its permissions and password unchanged: %s", admin_email)

    return user, created


def update_admin_account(email=None, password=None):
    admin_email = (email if email is not None else getattr(settings, "ADMIN_EMAIL", "")).strip()
    admin_password = password if password is not None else getattr(settings, "ADMIN_PASSWORD", "")
    if not admin_email:
        raise ValueError("An administrator email is required.")
    if not admin_password or len(admin_password) < 8:
        raise ValueError("An administrator password of at least 8 characters is required.")
    User = get_user_model()
    user = User.objects.get(email=admin_email)
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.set_password(admin_password)
    user.save()
    return user
