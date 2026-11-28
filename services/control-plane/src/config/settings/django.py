from pathlib import Path

from common.env import env, env_identifier, env_list

SERVICE_ROOT = Path(__file__).resolve().parents[3]
BASE_DIR = SERVICE_ROOT / "src"

SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-local-dev-change-me")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,control-plane")

INSTALLED_APPS = [
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
    "apps.auth.apps.AuthConfig",
    "apps.access.apps.AccessConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.registry.apps.RegistryConfig",
    "apps.training.apps.TrainingConfig",
    "apps.mlflow.apps.MLflowConfig",
    "apps.deployment.apps.DeploymentConfig",
    "apps.drift.apps.DriftConfig",
    "apps.observability.apps.ObservabilityConfig",
    "apps.production.apps.ProductionConfig",
    "apps.ct.apps.ContinuousTrainingConfig",
    "apps.notifications.apps.NotificationsConfig",
]

MIDDLEWARE = [
    "common.api.middleware.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = SERVICE_ROOT / "staticfiles"

LOGGING_CONFIG = "common.telemetry.logging.configure_logging"
LOGGING = {"version": 1}
