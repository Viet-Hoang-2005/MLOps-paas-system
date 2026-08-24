import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.registry.models import ModelVersion, RegistryAlias
from apps.registry.services.routing import predict_alias, predict_version


@pytest.mark.django_db
def test_version_endpoint_rejects_direct_manual_registration():
    user = get_user_model().objects.create_user("artifact-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="Artifact upload")

    client = APIClient()
    client.force_authenticate(user)
    response = client.post(
        f"/api/registry/models/{project.public_id}/versions/",
        {
            "version": "v1",
            "flavor": "sklearn",
            "source_artifact": SimpleUploadedFile("model.pkl", b"model-bytes", "application/octet-stream"),
        },
        format="multipart",
    )

    assert response.status_code == 405
    assert not ModelVersion.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_version_smoke_test_is_tenant_scoped(monkeypatch):
    owner = get_user_model().objects.create_user("smoke-owner@example.com", "password123")
    other = get_user_model().objects.create_user("smoke-other@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Smoke")
    version = ModelVersion.objects.create(project=project, version="1")
    client = APIClient()
    url = f"/api/registry/versions/{version.public_id}/smoke-test/"

    client.force_authenticate(other)
    assert client.post(url, {"features": {}} , format="json").status_code == 404

    client.force_authenticate(owner)
    calls = []

    def fake_predict_version(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    monkeypatch.setattr("apps.registry.api.endpoints.predict_version", fake_predict_version)
    response = client.post(url, {"features": {"value": 1}}, format="json")

    assert response.status_code == 200
    assert len(calls) == 1


class FakeResponse:
    status_code = 200

    def json(self):
        return {"prediction": [1], "confidence": [0.97]}


class FakeHttpClient:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return FakeResponse()


@pytest.fixture
def routable_version(db):
    user = get_user_model().objects.create_user("route-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="Routable")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="sklearn", status="ready")
    deployment = Deployment.objects.create(version=version, build=build, status="healthy")
    Endpoint.objects.create(
        deployment=deployment,
        public_url="https://models.example/predict",
        internal_url="http://worker:3000",
        health_status="healthy",
    )
    return project, version


def test_predict_version_proxies_to_healthy_endpoint(routable_version):
    _, version = routable_version
    http = FakeHttpClient()

    result = predict_version(version=version, payload={"features": {"value": 1}}, http=http)

    assert result["prediction"] == [1]
    assert result["confidence"] == [0.97]
    assert result["endpoint_url"] == "https://models.example/predict"
    assert http.calls == [
        ("POST", "http://worker:3000/predict", {"json": {"features": {"value": 1}}})
    ]


def test_predict_version_rejects_version_without_healthy_endpoint(routable_version):
    _, version = routable_version
    Endpoint.objects.update(health_status="unhealthy")

    with pytest.raises(ValidationError, match="no healthy endpoint"):
        predict_version(version=version, payload={}, http=FakeHttpClient())


def test_predict_alias_resolves_alias_and_rejects_missing_alias(routable_version):
    project, version = routable_version
    RegistryAlias.objects.create(project=project, version=version, name="production")

    result = predict_alias(project=project, alias_name="production", payload={}, http=FakeHttpClient())
    assert result["success"] is True

    with pytest.raises(NotFound, match="does not exist"):
        predict_alias(project=project, alias_name="missing", payload={}, http=FakeHttpClient())
