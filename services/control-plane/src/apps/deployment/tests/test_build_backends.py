from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, BuildInputAsset
from infrastructure.execution.argo_backends import ArgoBuildBackend
from infrastructure.execution.docker_backends import DockerBuildBackend


class RecordingStorage:
    bucket = "artifact-bucket"

    def __init__(self):
        self.downloaded_uri = ""
        self.downloaded_uris = []

    def presigned_get(self, uri, _ttl):
        self.downloaded_uri = uri
        self.downloaded_uris.append(uri)
        return "https://storage.example/download"

    @staticmethod
    def presigned_put(_uri, _ttl):
        return "https://storage.example/upload"


class SuccessfulContainer:
    id = "packager-container"

    @staticmethod
    def wait():
        return {"StatusCode": 0}

    @staticmethod
    def logs(stdout=True, stderr=True):
        assert stdout and stderr
        return b"build complete"

    @staticmethod
    def remove():
        return None


class RecordingDocker:
    def __init__(self):
        self.environment = None

    def run(self, **kwargs):
        self.environment = kwargs["environment"]
        return SuccessfulContainer()


def create_build_with_input():
    owner = get_user_model().objects.create_user("build-backend@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="build backend project")
    build = Build.objects.create(project=project, flavor="sklearn", backend="docker", status="building")
    asset = BuildInputAsset.objects.create(
        build=build,
        kind="source_artifact",
        name="model.pkl",
        s3_uri="s3://artifact-bucket/build-input/model.pkl",
    )
    return build, asset


@pytest.mark.django_db
def test_docker_build_backend_uses_build_input_s3_uri():
    build, asset = create_build_with_input()
    storage = RecordingStorage()
    docker = RecordingDocker()

    assert DockerBuildBackend(docker_client=docker, storage=storage).run(build) == "build complete"
    assert storage.downloaded_uri == asset.s3_uri
    assert docker.environment["SOURCE_DOWNLOAD_URL"] == "https://storage.example/download"
    assert docker.environment["PROJECT_ID"] == str(build.project.public_id)
    assert docker.environment["BUILD_ID"] == str(build.public_id)
    assert "MODEL_VERSION_ID" not in docker.environment
    assert docker.environment["IMAGE_REPOSITORY"] == f"image-{build.project.public_id}"
    assert docker.environment["IMAGE_TAG"] == f"build-{build.public_id}"


@pytest.mark.django_db
def test_argo_build_backend_uses_build_input_s3_uri():
    build, asset = create_build_with_input()
    storage = RecordingStorage()
    client = SimpleNamespace(trigger=lambda _url, payload: payload)

    result = ArgoBuildBackend(client=client, storage=storage).run(build)

    assert result["dispatched"] is True
    assert storage.downloaded_uri == asset.s3_uri
    assert result["response"]["source_download_url"] == "https://storage.example/download"
    assert result["response"]["project_id"] == str(build.project.public_id)
    assert result["response"]["image_repository"].endswith(f"image-{build.project.public_id}")
    assert result["response"]["image_tag"] == f"build-{build.public_id}"


@pytest.mark.django_db
@pytest.mark.parametrize("backend_name", ["docker", "argo"])
def test_build_backend_passes_uploaded_label_mapping_to_packager(backend_name):
    build, source = create_build_with_input()
    mapping = BuildInputAsset.objects.create(
        build=build,
        kind="label_mapping",
        name="label_classes_v1.json",
        s3_uri="s3://artifact-bucket/build-input/label_classes_v1.json",
    )
    storage = RecordingStorage()
    if backend_name == "docker":
        docker = RecordingDocker()
        DockerBuildBackend(docker_client=docker, storage=storage).run(build)
        data = docker.environment
        assert data["LABEL_MAPPING_DOWNLOAD_URL"] == "https://storage.example/download"
        assert data["LABEL_MAPPING_FILENAME"] == mapping.name
    else:
        client = SimpleNamespace(trigger=lambda _url, payload: payload)
        data = ArgoBuildBackend(client=client, storage=storage).run(build)["response"]
        assert data["label_mapping_download_url"] == "https://storage.example/download"
        assert data["label_mapping_filename"] == mapping.name
    assert storage.downloaded_uris == [mapping.s3_uri, source.s3_uri]


@pytest.mark.django_db
@pytest.mark.parametrize("backend_name", ["docker", "argo"])
def test_build_backend_keeps_label_mapping_optional(backend_name):
    build, _ = create_build_with_input()
    storage = RecordingStorage()
    if backend_name == "docker":
        docker = RecordingDocker()
        DockerBuildBackend(docker_client=docker, storage=storage).run(build)
        assert docker.environment["LABEL_MAPPING_DOWNLOAD_URL"] == ""
        assert docker.environment["LABEL_MAPPING_FILENAME"] == ""
    else:
        client = SimpleNamespace(trigger=lambda _url, payload: payload)
        data = ArgoBuildBackend(client=client, storage=storage).run(build)["response"]
        assert data["label_mapping_download_url"] == ""
        assert data["label_mapping_filename"] == ""
