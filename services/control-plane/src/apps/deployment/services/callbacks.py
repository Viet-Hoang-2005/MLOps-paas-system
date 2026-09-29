"""Short-lived reporter capabilities bound to one deployment UUID."""

import hashlib
import hmac
import time

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

CALLBACK_TTL_SECONDS = 3600


def _key():
    value = settings.CONTROL_PLANE_WEBHOOK_SECRET
    if not value:
        raise ImproperlyConfigured("Deployment reporter secret is required.")
    return value.encode()


def issue_callback_token(deployment_id):
    expires = int(time.time()) + CALLBACK_TTL_SECONDS
    signature = hmac.new(
        _key(),
        f"deployment:{deployment_id}:{expires}".encode(), hashlib.sha256,
    ).hexdigest()
    return f"{expires}.{signature}"


def valid_callback_token(token, deployment_id):
    try:
        expires_text, signature = token.split(".", 1)
        expires = int(expires_text)
        now = int(time.time())
        if not now <= expires <= now + CALLBACK_TTL_SECONDS:
            return False
        expected = hmac.new(
            _key(),
            f"deployment:{deployment_id}:{expires}".encode(), hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError, TypeError):
        return False
