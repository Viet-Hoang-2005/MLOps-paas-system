"""Opt-in integration settings for a disposable PostgreSQL server, never app data."""

import os

from .test import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ["PGTEST_HOST"],
        "PORT": os.environ["PGTEST_PORT"],
        "NAME": os.environ["PGTEST_DB"],
        "USER": os.environ["PGTEST_USER"],
        "PASSWORD": os.environ.get("PGTEST_PASSWORD", ""),
        "TEST": {"NAME": "test_control_plane_build_callbacks"},
    }
}
