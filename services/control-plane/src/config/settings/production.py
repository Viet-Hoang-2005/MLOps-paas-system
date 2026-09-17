from common.env import env, env_bool, env_int
from django.core.exceptions import ImproperlyConfigured

from .base import *

SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
JWT_PRIVATE_KEY = env("JWT_PRIVATE_KEY", required=True).replace("\\n", "\n")
JWT_PUBLIC_KEY = env("JWT_PUBLIC_KEY", required=True).replace("\\n", "\n")
CONTROL_PLANE_WEBHOOK_SECRET = env("CONTROL_PLANE_WEBHOOK_SECRET", required=True)
if len(CONTROL_PLANE_WEBHOOK_SECRET) < 32:
    raise ImproperlyConfigured("CONTROL_PLANE_WEBHOOK_SECRET must contain at least 32 characters")
ARGO_EVENTS_WEBHOOK_TOKEN = env("ARGO_EVENTS_WEBHOOK_TOKEN", required=True)
if len(ARGO_EVENTS_WEBHOOK_TOKEN) < 32:
    raise ImproperlyConfigured("ARGO_EVENTS_WEBHOOK_TOKEN must contain at least 32 characters")

POD_IP = str(env("POD_IP", "")).strip()
if POD_IP and POD_IP not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, POD_IP]

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_REDIRECT_EXEMPT = [r"^health/"]
SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SIMPLE_JWT.update({"ALGORITHM": "RS256", "SIGNING_KEY": JWT_PRIVATE_KEY, "VERIFYING_KEY": JWT_PUBLIC_KEY})