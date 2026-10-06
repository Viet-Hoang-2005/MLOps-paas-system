from datetime import timedelta
from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def get_cookie_config():
    lifetime = settings.SIMPLE_JWT.get("REFRESH_TOKEN_LIFETIME", timedelta(days=1))
    max_age = int(lifetime.total_seconds())
    return {
        "key": getattr(settings, "AUTH_COOKIE_NAME", "refresh_token"),
        "max_age": max_age,
        "httponly": True,
        "samesite": getattr(settings, "AUTH_COOKIE_SAMESITE", "Lax"),
        "secure": getattr(settings, "AUTH_COOKIE_SECURE", False),
        "path": getattr(settings, "AUTH_COOKIE_PATH", "/api/auth/"),
    }


def set_refresh_token_cookie(response, refresh_token: str):
    config = get_cookie_config()
    response.set_cookie(
        key=config["key"],
        value=refresh_token,
        max_age=config["max_age"],
        httponly=config["httponly"],
        samesite=config["samesite"],
        secure=config["secure"],
        path=config["path"],
    )


def clear_refresh_token_cookie(response):
    config = get_cookie_config()
    response.delete_cookie(
        key=config["key"],
        path=config["path"],
        samesite=config["samesite"],
    )


def get_refresh_token_from_request(request) -> str | None:
    cookie_name = getattr(settings, "AUTH_COOKIE_NAME", "refresh_token")
    return request.COOKIES.get(cookie_name)


def verify_auth_security_headers(request):
    """
    Guards cookie-based authentication endpoints against CSRF.
    """
    # A cross-origin browser request with this header requires a successful CORS preflight.
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        raise PermissionDenied("Missing or invalid security header (X-Requested-With).")

    # Cookie-bearing browser requests must always identify an allowlisted origin.
    origin = request.headers.get("Origin")
    if not origin:
        raise PermissionDenied("Origin header is required.")

    allowed = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
    clean_origin = origin.rstrip("/")
    clean_allowed = [str(value).rstrip("/") for value in allowed]
    if clean_origin not in clean_allowed:
        raise PermissionDenied("Origin not allowed.")

