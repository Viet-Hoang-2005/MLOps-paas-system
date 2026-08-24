import os
import re

from django.core.exceptions import ImproperlyConfigured


def env(name, default=None, *, required=False):
    value = os.environ.get(name, default)
    if required and (value is None or str(value).strip() == ""):
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return value


def env_bool(name, default=False):
    value = env(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    try:
        return int(env(name, default))
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(f"{name} must be an integer") from exc


def env_list(name, default=""):
    return [item.strip() for item in str(env(name, default)).split(",") if item.strip()]


def env_identifier(name, default):
    value = str(env(name, default)).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ImproperlyConfigured(f"{name} must be a PostgreSQL identifier")
    return value
