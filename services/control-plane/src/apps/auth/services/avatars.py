"""One current avatar per account; upload before locking and clean after commit."""

import logging
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from PIL import Image
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

logger = logging.getLogger(__name__)
MAX_AVATAR_BYTES = 5 * 1024 * 1024


def validate_avatar(upload):
    if upload.size > MAX_AVATAR_BYTES:
        raise serializers.ValidationError({"avatar": "Avatar must be 5 MiB or smaller."})
    try:
        upload = serializers.ImageField().run_validation(upload)
    except (serializers.ValidationError, DjangoValidationError) as exc:
        raise serializers.ValidationError({"avatar": exc.detail if hasattr(exc, "detail") else exc.messages}) from exc
    upload.content_type = Image.MIME.get(upload.image.format, "application/octet-stream")
    upload.seek(0)
    return upload


def avatar_storage():
    return get_user_model()._meta.get_field("avatar").storage


def cleanup_avatar(tenant_id, key):
    """Never delete a prefix, another tenant's key, or an active avatar."""
    prefix = f"users/{tenant_id}/avatar/"
    if not key or not key.startswith(prefix) or "/" in key[len(prefix) :] or key[len(prefix) :] in {"", ".", ".."}:
        raise ValueError("Invalid avatar storage scope.")
    if get_user_model().objects.filter(avatar=key).exists():
        return
    avatar_storage().delete(key)


def schedule_cleanup(tenant_id, key):
    if not key:
        return
    from apps.auth.tasks import delete_avatar_object

    try:
        delete_avatar_object.delay(tenant_id, key)
    except Exception:
        # A broker outage must not turn an already committed profile update into a failure.
        logger.warning("Avatar cleanup dispatch failed; attempting storage cleanup.", exc_info=True)
        try:
            cleanup_avatar(tenant_id, key)
        except Exception:
            logger.exception("Avatar cleanup failed; the unreferenced object needs cleanup.")


def update_profile(user, *, changes=None, avatar=None, remove=False, only_if_empty=False):
    if avatar is not None and remove:
        raise serializers.ValidationError({"avatar": "Upload and remove_avatar cannot be combined."})
    key = None
    committed = False
    if avatar is not None:
        avatar = validate_avatar(avatar)
        suffix = avatar.image.format.lower()
        intended_key = f"users/{user.tenant_id}/avatar/{uuid.uuid4().hex}.{suffix}"
        try:
            key = avatar_storage().save(intended_key, avatar)
        except Exception:
            # The upload may have reached storage before its response was lost.
            schedule_cleanup(user.tenant_id, intended_key)
            raise
    try:
        with transaction.atomic():
            current = get_user_model().objects.select_for_update().get(pk=user.pk)
            if not current.is_active:
                raise PermissionDenied("Account is disabled.")
            previous = current.avatar.name if current.avatar else ""
            fields = dict(changes or {})
            if key and not (only_if_empty and previous):
                fields["avatar"] = key
            elif remove:
                fields["avatar"] = None
            for field, value in fields.items():
                setattr(current, field, value)
            if fields:
                current.save(update_fields=list(fields))
            next_key = current.avatar.name if current.avatar else ""
            if previous and previous != next_key:
                transaction.on_commit(lambda: schedule_cleanup(current.tenant_id, previous))
            if key and key != next_key:
                transaction.on_commit(lambda: schedule_cleanup(current.tenant_id, key))
        committed = True
        return current
    finally:
        if key and not committed:
            schedule_cleanup(user.tenant_id, key)
