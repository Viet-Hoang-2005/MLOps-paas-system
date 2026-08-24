from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from infrastructure.execution.docker_backends import DockerDeploymentBackend

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment
from apps.registry.models import ModelVersion


class HealthyResponse:
    @staticmethod
    def json():
        return {"status": "healthy", "model_loaded": True}


class HealthyHttpClient:
    def request(self, method, url):
        assert method == "GET"
        assert url.endswith(":5001/health")
        return HealthyResponse()


class RecordingDockerClient:
    def __init__(self):
        self.kwargs = None

    def run(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(id="runtime-container-id")


@pytest.mark.django_db
def test_local_deployment_uses_embedded_model_artifact_and_becomes_healthy():
    owner = get_user_model().objects.create_user("runtime-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="runtime model")
    version = ModelVersion.objects.create(project=project, version="1", flavor="xgboost")
    build = Build.objects.create(
        project=project,
        version=version,
        flavor="xgboost",
        status="ready",
        image_uri=f"image-{project.public_id}:v1",
        image_digest="sha256:local-image-id",
    )
    deployment = Deployment.objects.create(version=version, build=build, status="deploying")
    docker = RecordingDockerClient()

    endpoint = DockerDeploymentBackend(docker_client=docker, http=HealthyHttpClient()).deploy(deployment)

    assert docker.kwargs["environment"] == {
        "PROJECT_ID": str(project.public_id),
        "MODEL_VERSION_ID": str(version.public_id),
        "MODEL_VERSION": "1",
        "MODEL_URI": "/app/model_artifact",
        "TENANT_ID": owner.tenant_id,
    }
    assert docker.kwargs["image"] == "sha256:local-image-id"
    assert endpoint.internal_url == f"http://deploy-{build.public_id}:5001"
    assert endpoint.health_status == "healthy"


def test_health_requires_healthy_payload_status():
    class UnhealthyHttpClient:
        @staticmethod
        def request(_method, _url):
            return SimpleNamespace(json=lambda: {"status": "unhealthy", "model_loaded": True})

    endpoint = SimpleNamespace(internal_url="http://worker:5001")
    deployment = SimpleNamespace(endpoint=endpoint)

    healthy, payload = DockerDeploymentBackend(
        docker_client=SimpleNamespace(),
        http=UnhealthyHttpClient(),
    ).health(deployment)

    assert healthy is False
    assert payload["status"] == "unhealthy"
