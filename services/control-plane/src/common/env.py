import os
import re
from typing import Optional

from django.core.exceptions import ImproperlyConfigured


def env(name: str, default: Optional[str] = None, *, required: bool = False) -> Optional[str]:
    value = os.environ.get(name, default)
    if required and (value is None or value.strip() == ""):
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = env(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(f"{name} must be an integer") from exc


def env_list(name: str, default: str = "") -> list[str]:
    value = env(name, default)
    if value is None:
        value = default
    return [item.strip() for item in value.split(",") if item.strip()]


def env_identifier(name: str, default: str) -> str:
    value = env(name, default)
    if value is None:
        value = default
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ImproperlyConfigured(f"{name} must be a PostgreSQL identifier")
    return value
