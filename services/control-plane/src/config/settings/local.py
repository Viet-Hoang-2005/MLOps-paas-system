from common.env import env_bool

from .base import *

DEBUG = env_bool("DJANGO_DEBUG", True)
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
