import importlib

from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, override_settings


def test_production_settings_exempt_health_endpoints_from_ssl_redirect(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-production-secret-key")
    monkeypatch.setenv("JWT_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("JWT_PUBLIC_KEY", "test-public-key")
    monkeypatch.setenv("CONTROL_PLANE_WEBHOOK_SECRET", "test-webhook-secret-with-at-least-32-characters")

    production_settings = importlib.import_module("config.settings.production")

    assert production_settings.SECURE_REDIRECT_EXEMPT == [r"^health/"]


@override_settings(SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r"^health/"])
def test_kubelet_health_request_is_not_redirected_before_host_validation():
    request = RequestFactory().get("/health/live", HTTP_HOST="10.42.2.44:8000")
    middleware = SecurityMiddleware(lambda _request: HttpResponse(status=200))

    response = middleware(request)

    assert response.status_code == 200

