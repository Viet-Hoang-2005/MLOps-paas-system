from datetime import timedelta

from corsheaders.defaults import default_headers

from common.env import env, env_bool, env_int, env_list

from .django import SECRET_KEY

JWT_PRIVATE_KEY = env("JWT_PRIVATE_KEY", "").replace("\\n", "\n")
JWT_PUBLIC_KEY = env("JWT_PUBLIC_KEY", "").replace("\\n", "\n")
JWT_ALGORITHM = "RS256" if JWT_PRIVATE_KEY and JWT_PUBLIC_KEY else "HS256"
PASSWORD_RESET_THROTTLE_RATE = env("PASSWORD_RESET_THROTTLE_RATE", "10/minute")
REGISTRATION_THROTTLE_RATE = env("REGISTRATION_THROTTLE_RATE", "10/minute")
PASSWORD_CHANGE_THROTTLE_RATE = env("PASSWORD_CHANGE_THROTTLE_RATE", "10/minute")
LOGIN_IP_THROTTLE_RATE = env("LOGIN_IP_THROTTLE_RATE", "30/minute")
LOGIN_ACCOUNT_THROTTLE_RATE = env("LOGIN_ACCOUNT_THROTTLE_RATE", "10/minute")
# Reverse proxies in front of the app that append to X-Forwarded-For. 0 trusts
# only the socket address, so the header can never choose the throttle key.
TRUSTED_PROXY_COUNT = env_int("TRUSTED_PROXY_COUNT", 0)
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "common.api.pagination.DefaultPagination",
    "EXCEPTION_HANDLER": "common.api.exceptions.exception_handler",
    "NUM_PROXIES": TRUSTED_PROXY_COUNT,
    "DEFAULT_THROTTLE_RATES": {
        "password_reset": PASSWORD_RESET_THROTTLE_RATE,
        "registration": REGISTRATION_THROTTLE_RATE,
        "password_change": PASSWORD_CHANGE_THROTTLE_RATE,
        "login_ip": LOGIN_IP_THROTTLE_RATE,
        "login_account": LOGIN_ACCOUNT_THROTTLE_RATE,
    },
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": JWT_ALGORITHM,
    "SIGNING_KEY": JWT_PRIVATE_KEY or SECRET_KEY,
    "VERIFYING_KEY": JWT_PUBLIC_KEY,
    "AUDIENCE": "mlops-paas",
    "ISSUER": "django-control-plane",
}

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
CORS_EXPOSE_HEADERS = ["Content-Disposition"]
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
CORS_ALLOW_HEADERS = (*default_headers, "idempotency-key", "x-requested-with")

AUTH_COOKIE_NAME = "refresh_token"
AUTH_COOKIE_SECURE = env_bool("AUTH_COOKIE_SECURE", False)
AUTH_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE", "Lax")
AUTH_COOKIE_PATH = env("AUTH_COOKIE_PATH", "/api/auth/")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
GOOGLE_OAUTH2_CLIENT_ID = env("GOOGLE_OAUTH2_CLIENT_ID", "")
GITHUB_OAUTH2_CLIENT_ID = env("GITHUB_OAUTH2_CLIENT_ID", "")
GITHUB_OAUTH2_CLIENT_SECRET = env("GITHUB_OAUTH2_CLIENT_SECRET", "")
