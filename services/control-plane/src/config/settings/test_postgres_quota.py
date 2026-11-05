"""Use an explicitly supplied disposable PostgreSQL instance for locking tests."""

import os

from .test import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "postgres",
                         "USER": "postgres", "HOST": "127.0.0.1", "PORT": os.environ["QUOTA_TEST_PG_PORT"],
                         "TEST": {"NAME": "test_training_quota"}}}
