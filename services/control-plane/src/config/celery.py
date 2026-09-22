import os

from celery import Celery

import common.celery_logging  # noqa: F401
import common.metrics  # noqa: F401

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("control_plane")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
