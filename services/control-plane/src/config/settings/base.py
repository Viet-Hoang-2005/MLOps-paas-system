from datetime import timedelta
from pathlib import Path

from common.env import env, env_identifier, env_int, env_list
from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured

SERVICE_ROOT = Path(__file__).resolve().parents[3]
BASE_DIR = SERVICE_ROOT / "src"

SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-local-dev-change-me")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,control-plane")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "storages",
    "channels",
    "apps.auth.apps.AuthConfig",
    "apps.access.apps.AccessConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.registry.apps.RegistryConfig",
    "apps.training.apps.TrainingConfig",
    "apps.deployment.apps.DeploymentConfig",
    "apps.drift.apps.DriftConfig",
    "apps.observability.apps.ObservabilityConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "common.middleware.RequestContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DB_SCHEMA = env_identifier("DB_SCHEMA", "control_plane")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "mlops_paas_db"),
        "USER": env("DB_USER", "postgres"),
        "PASSWORD": env("DB_PASSWORD", "postgres"),
        "HOST": env("DB_HOST_RW", "postgres"),
        "PORT": env("DB_PORT", "5432"),
        "OPTIONS": {"options": f"-c search_path={DB_SCHEMA},public"},
    }
}

AUTH_USER_MODEL = "identity.CustomUser"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

JWT_PRIVATE_KEY = env("JWT_PRIVATE_KEY", "")
JWT_PUBLIC_KEY = env("JWT_PUBLIC_KEY", "")
JWT_ALGORITHM = "RS256" if JWT_PRIVATE_KEY and JWT_PUBLIC_KEY else "HS256"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "common.api.pagination.DefaultPagination",
    "EXCEPTION_HANDLER": "common.api.exceptions.exception_handler",
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": JWT_ALGORITHM,
    "SIGNING_KEY": JWT_PRIVATE_KEY or SECRET_KEY,
    "VERIFYING_KEY": JWT_PUBLIC_KEY,
    "AUDIENCE": "mlops-paas",
    "ISSUER": "django-control-plane",
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
CORS_ALLOW_HEADERS = (*default_headers, "idempotency-key")
STATIC_URL = "/static/"
STATIC_ROOT = SERVICE_ROOT / "staticfiles"

REDIS_URL = env("REDIS_URL", "redis://redis:6379/1")
REDPANDA_BROKERS = env("REDPANDA_BROKERS", "redpanda:9092")
CACHES = {"default": {"BACKEND": "django_redis.cache.RedisCache", "LOCATION": REDIS_URL}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}}
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://redis:6379/3")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://redis:6379/4")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 43200)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 42600)
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CONTROL_PLANE_WEBHOOK_SECRET = env("CONTROL_PLANE_WEBHOOK_SECRET", "local-webhook-secret")
ARGO_EVENTS_WEBHOOK_TOKEN = env("ARGO_EVENTS_WEBHOOK_TOKEN", "")
CONTROL_PLANE_INTERNAL_URL = str(env("CONTROL_PLANE_INTERNAL_URL", "http://control-plane:8000")).rstrip("/")
TRAINING_PRESIGNED_URL_TTL_SECONDS = env_int("TRAINING_PRESIGNED_URL_TTL_SECONDS", 900)
TRAINING_CAPABILITY_GRACE_SECONDS = env_int("TRAINING_CAPABILITY_GRACE_SECONDS", 900)
TRAINING_CAPABILITY_MAX_TTL_SECONDS = env_int("TRAINING_CAPABILITY_MAX_TTL_SECONDS", 7200)
MODEL_SERVER_PUBLIC_URL = str(env("MODEL_SERVER_PUBLIC_URL", "http://localhost:5002")).rstrip("/")
MODEL_SERVER_INTERNAL_URL = str(env("MODEL_SERVER_INTERNAL_URL", "http://traefik:5000")).rstrip("/")
MODEL_RUNTIME_NAMESPACE = str(env("MODEL_RUNTIME_NAMESPACE", "mlops-model-runtimes")).strip()
DOCKER_NETWORK_NAME = env("DOCKER_NETWORK_NAME", "mlops_paas_network")
EXECUTION_BACKEND = str(env("EXECUTION_BACKEND", "docker")).strip().lower()
if EXECUTION_BACKEND not in {"docker", "argo"}:
    raise ImproperlyConfigured("EXECUTION_BACKEND must be either 'docker' or 'argo'")


def execution_backend_override(name):
    value = str(env(name, "") or EXECUTION_BACKEND).strip().lower()
    if value not in {"docker", "argo"}:
        raise ImproperlyConfigured(f"{name} must be either 'docker' or 'argo'")
    return value


# Component-specific values support gradual migrations; EXECUTION_BACKEND is the normal default.
BUILD_BACKEND = execution_backend_override("BUILD_BACKEND")
DEPLOYMENT_BACKEND = execution_backend_override("DEPLOYMENT_BACKEND")
TRAINING_BACKEND = execution_backend_override("TRAINING_BACKEND")
DRIFT_BACKEND = execution_backend_override("DRIFT_BACKEND")
TRAINING_ENABLED = str(env("TRAINING_ENABLED", "true")).lower() in {
    "1",
    "true",
    "yes",
    "on",
}
TRAINING_GPU_ENABLED = str(env("TRAINING_GPU_ENABLED", "true" if TRAINING_BACKEND == "argo" else "false")).lower() in {
    "1",
    "true",
    "yes",
    "on",
}
TRAINING_GPU_COUNTS = tuple(
    int(value)
    for value in env_list("TRAINING_GPU_COUNTS", "1")
    if str(value).strip().isdigit() and int(value) > 0
)
ARGO_BUILD_WEBHOOK_URL = env("ARGO_BUILD_WEBHOOK_URL", "")
ARGO_TRAINING_WEBHOOK_URL = env("ARGO_TRAINING_WEBHOOK_URL", "")
ARGO_CANCEL_TRAINING_WEBHOOK_URL = env("ARGO_CANCEL_TRAINING_WEBHOOK_URL", "")
ARGO_DRIFT_WEBHOOK_URL = env("ARGO_DRIFT_WEBHOOK_URL", "")
ARGO_DEPLOY_WEBHOOK_URL = env("ARGO_DEPLOY_WEBHOOK_URL", "")
ARGO_DELETE_WEBHOOK_URL = env("ARGO_DELETE_WEBHOOK_URL", "")
MLFLOW_TRACKING_URI = env("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MLFLOW_UI_URL = str(env("MLFLOW_UI_URL", "http://localhost:5003")).rstrip("/")
PROMETHEUS_INTERNAL_URL = str(env("PROMETHEUS_INTERNAL_URL", "")).rstrip("/")

AWS_STORAGE_BUCKET_NAME = env("AWS_BUCKET_NAME", "mlops-paas-artifacts")
AWS_S3_REGION_NAME = env("AWS_DEFAULT_REGION", "ap-southeast-1")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", "") or None
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = True
AWS_S3_FILE_OVERWRITE = False
STORAGES = {
    "default": {"BACKEND": "storages.backends.s3.S3Storage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

HARBOR_REGISTRY_URL = str(env("HARBOR_REGISTRY_URL", "")).strip().rstrip("/")
HARBOR_USER_PROJECT = env("HARBOR_USER_PROJECT", "user-images")
HARBOR_USERNAME = env("HARBOR_USERNAME", "")
HARBOR_PASSWORD = env("HARBOR_PASSWORD", "")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
GOOGLE_OAUTH2_CLIENT_ID = env("GOOGLE_OAUTH2_CLIENT_ID", "")
GITHUB_OAUTH2_CLIENT_ID = env("GITHUB_OAUTH2_CLIENT_ID", "")
GITHUB_OAUTH2_CLIENT_SECRET = env("GITHUB_OAUTH2_CLIENT_SECRET", "")
GITHUB_OAUTH_REDIRECT_URI = env("GITHUB_OAUTH_REDIRECT_URI", "http://localhost:5173/oauth/github/callback")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "common.logging.JsonFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
