import importlib

from django.http import HttpResponse
from django.middleware.common import CommonMiddleware
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, override_settings


def test_production_settings_exempt_health_endpoints_from_ssl_redirect(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-production-secret-key")
    monkeypatch.setenv("JWT_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("JWT_PUBLIC_KEY", "test-public-key")
    monkeypatch.setenv("CONTROL_PLANE_WEBHOOK_SECRET", "test-webhook-secret-with-at-least-32-characters")
    monkeypatch.setenv("ARGO_EVENTS_WEBHOOK_TOKEN", "x" * 32)
    monkeypatch.setenv("POD_IP", "10.42.2.44")

    production_settings = importlib.import_module("config.settings.production")

    assert production_settings.SECURE_REDIRECT_EXEMPT == [
        r"^health/",
        r"^internal/",
        r"^api/auth/\.well-known/jwks\.json$",
    ]
    assert "10.42.2.44" in production_settings.ALLOWED_HOSTS


@override_settings(
    ALLOWED_HOSTS=["10.42.2.44"],
    SECURE_SSL_REDIRECT=True,
    SECURE_REDIRECT_EXEMPT=[r"^health/"],
)
def test_kubelet_health_request_is_not_redirected_before_host_validation():
    request = RequestFactory().get("/health/live", HTTP_HOST="10.42.2.44:8000")
    middleware = SecurityMiddleware(CommonMiddleware(lambda _request: HttpResponse(status=200)))

    response = middleware(request)

    assert response.status_code == 200


@override_settings(
    ALLOWED_HOSTS=["mlops-paas-control-plane.mlops-control-plane.svc.cluster.local"],
    SECURE_SSL_REDIRECT=True,
    SECURE_REDIRECT_EXEMPT=[r"^api/auth/\.well-known/jwks\.json$"],
)
def test_in_cluster_jwks_request_is_not_redirected():
    # The model gateway verifies user JWTs with keys fetched over in-cluster HTTP.
    factory = RequestFactory()
    host = "mlops-paas-control-plane.mlops-control-plane.svc.cluster.local:8000"
    middleware = SecurityMiddleware(CommonMiddleware(lambda _request: HttpResponse(status=200)))

    assert middleware(factory.get("/api/auth/.well-known/jwks.json", HTTP_HOST=host)).status_code == 200
    assert middleware(factory.get("/api/auth/token/", HTTP_HOST=host)).status_code == 301
