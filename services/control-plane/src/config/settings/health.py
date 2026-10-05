"""Background health processes need DB/broker access, not signing or AWS secrets."""

from common.env import env

from .base import *  # noqa: F403

SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
DEBUG = False
