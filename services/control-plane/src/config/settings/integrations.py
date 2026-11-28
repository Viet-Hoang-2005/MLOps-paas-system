from common.env import env, env_int

LOKI_URL = str(env("LOKI_URL", "")).rstrip("/")
REDPANDA_BROKERS = env("REDPANDA_BROKERS", "redpanda:9092")

PROMETHEUS_INTERNAL_URL = str(env("PROMETHEUS_INTERNAL_URL", "")).rstrip("/")

AWS_STORAGE_BUCKET_NAME = env("AWS_BUCKET_NAME", "mlops-paas-artifacts")
AWS_S3_REGION_NAME = env("AWS_DEFAULT_REGION", "ap-southeast-1")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", "") or None
AWS_S3_PUBLIC_ENDPOINT_URL = env("AWS_S3_PUBLIC_ENDPOINT_URL", "") or None
AWS_S3_ADDRESSING_STYLE = "path" if AWS_S3_ENDPOINT_URL else "auto"
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = True
AWS_S3_FILE_OVERWRITE = False
STORAGES = {
    "default": {"BACKEND": "infrastructure.storage.django_storage.PublicPresignedS3Storage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

HARBOR_REGISTRY_URL = str(env("HARBOR_REGISTRY_URL", "")).strip().rstrip("/")
HARBOR_USER_PROJECT = env("HARBOR_USER_PROJECT", "user-images")
HARBOR_USERNAME = env("HARBOR_USERNAME", "")
HARBOR_PASSWORD = env("HARBOR_PASSWORD", "")

# MLflow Artifact Limits (default: 5 GiB)
MLFLOW_MAX_ARTIFACT_UPLOAD_SIZE_BYTES = env_int("MLFLOW_MAX_ARTIFACT_UPLOAD_SIZE_BYTES", 5 * 1024 * 1024 * 1024)
MLFLOW_MAX_ARTIFACT_DOWNLOAD_SIZE_BYTES = env_int("MLFLOW_MAX_ARTIFACT_DOWNLOAD_SIZE_BYTES", 5 * 1024 * 1024 * 1024)
