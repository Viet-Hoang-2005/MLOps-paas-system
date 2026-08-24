import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build
from apps.deployment.services import logs as log_service
from apps.registry.models import ModelVersion


class FakeRedis:
    def __init__(self, lines):
        self.lines = lines

    def lrange(self, _key, start, _end):
        return self.lines[start:]

    def llen(self, _key):
        return len(self.lines)


@pytest.mark.django_db
def test_build_logs_streams_redis_lines_for_build_owner(monkeypatch):
    owner = get_user_model().objects.create_user("build-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="build logs")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="sklearn", status="building")
    monkeypatch.setattr(log_service.Redis, "from_url", lambda _url: FakeRedis([b"first", b"second"]))
    client = APIClient()
    client.force_authenticate(owner)

    response = client.get(f"/api/builds/{build.public_id}/logs/?offset=1")

    assert response.status_code == 200
    assert response.data == {
        "build_id": str(build.public_id),
        "logs": ["second"],
        "next_offset": 2,
        "status": "building",
        "error_message": "",
    }


@pytest.mark.django_db
def test_build_logs_falls_back_to_persisted_history_when_redis_is_unavailable(monkeypatch):
    owner = get_user_model().objects.create_user("history-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="build history")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="sklearn", status="ready", logs="one\ntwo")
    monkeypatch.setattr(log_service.Redis, "from_url", lambda _url: (_ for _ in ()).throw(log_service.RedisError()))
    client = APIClient()
    client.force_authenticate(owner)

    response = client.get(f"/api/builds/{build.public_id}/logs/?offset=1")

    assert response.status_code == 200
    assert response.data["logs"] == ["two"]
    assert response.data["next_offset"] == 2


@pytest.mark.django_db
def test_build_logs_are_tenant_scoped_and_validate_offset():
    owner = get_user_model().objects.create_user("logs-owner@example.com", "password123")
    other = get_user_model().objects.create_user("logs-other@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="private logs")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="sklearn")
    client = APIClient()
    client.force_authenticate(other)

    assert client.get(f"/api/builds/{build.public_id}/logs/").status_code == 404

    client.force_authenticate(owner)
    invalid = client.get(f"/api/builds/{build.public_id}/logs/?offset=-1")
    assert invalid.status_code == 400
    assert invalid.data["error"]["detail"]["offset"] == "Must be a non-negative integer."


@pytest.mark.django_db
def test_deployment_logs_stream_runtime_progress_for_owner(monkeypatch):
    owner = get_user_model().objects.create_user("deployment-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="deployment logs")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="sklearn", status="ready")
    from apps.deployment.models import Deployment

    deployment = Deployment.objects.create(version=version, build=build, status="deploying")
    monkeypatch.setattr(log_service.Redis, "from_url", lambda _url: FakeRedis([b"starting", b"healthy"]))
    client = APIClient()
    client.force_authenticate(owner)

    response = client.get(f"/api/deployments/{deployment.public_id}/logs/?offset=1")

    assert response.status_code == 200
    assert response.data["logs"] == ["healthy"]
    assert response.data["next_offset"] == 2
    assert response.data["status"] == "deploying"
