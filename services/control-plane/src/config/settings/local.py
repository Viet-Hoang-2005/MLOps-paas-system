import os

from common.env import env, env_bool

from .base import *

DEBUG = env_bool("DJANGO_DEBUG", True)
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)

_access_key = env("AWS_ACCESS_KEY_ID", "").strip()
_secret_key = env("AWS_SECRET_ACCESS_KEY", "").strip()
_has_real_aws_keys = bool(_access_key and _secret_key and _access_key != "minioadmin")

if AWS_S3_ENDPOINT_URL is None and not _has_real_aws_keys:
    AWS_S3_ENDPOINT_URL = "http://minio:9000"
    AWS_S3_PUBLIC_ENDPOINT_URL = AWS_S3_PUBLIC_ENDPOINT_URL or "http://localhost:9000"
    AWS_S3_ADDRESSING_STYLE = "path"

if AWS_S3_ENDPOINT_URL:
    if not _access_key:
        os.environ["AWS_ACCESS_KEY_ID"] = env("MINIO_ROOT_USER", "").strip() or "minioadmin"
    if not _secret_key:
        os.environ["AWS_SECRET_ACCESS_KEY"] = env("MINIO_ROOT_PASSWORD", "").strip() or "minioadmin"
