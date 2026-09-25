import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment
from apps.registry.models import ModelVersion
from apps.registry.tests.factories import create_model_version
from apps.training.models import TrainingJob


class FakeStorage:
    bucket = "test-bucket"

    @staticmethod
    def parse_uri(uri):
        from urllib.parse import urlparse
        parsed = urlparse(uri)
        return parsed.netloc, parsed.path.lstrip("/")

    @staticmethod
    def put(_key, _file, _content_type):
        return None


@pytest.mark.django_db
def test_training_job_paths_are_project_scoped(monkeypatch):
    user = get_user_model().objects.create_user("owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")
    client = APIClient()
    client.force_authenticate(user)
    monkeypatch.setattr("apps.training.services.jobs.S3Storage", FakeStorage)

    response = client.post(
        "/api/training-jobs/",
        {
            "project": str(project.public_id),
            "name": "nightly",
            "model_flavor": "xgboost",
            "requirements_text": "xgboost==2.0.3",
            "source_zip": SimpleUploadedFile("source.zip", b"zip", "application/zip"),
            "training_data": SimpleUploadedFile("train.csv", b"x\n1\n", "text/csv"),
        },
        format="multipart",
    )

    assert response.status_code == 201
    job = TrainingJob.objects.get(public_id=response.data["id"])
    prefix = f"users/{user.tenant_id}/models/{project.public_id}/training/jobs/{job.public_id}"
    assert job.code_snapshot_uri.endswith(f"{prefix}/input/code/source.zip")
    assert job.data_snapshot_uri.endswith(f"{prefix}/input/data/train.csv")
    assert job.output_uri.endswith(f"{prefix}/output/model.tar.gz")
    assert job.mlflow_artifact_uri.endswith(f"{prefix}/mlflow/")
    assert "other-tenant" not in job.code_snapshot_uri
    assert "other-tenant" not in job.data_snapshot_uri

    monkeypatch.setattr(
        "apps.training.api.endpoints.output_download_url",
        lambda selected_job: "https://s3.example/download",
    )
    download = client.get(f"/api/training-jobs/{job.public_id}/download/")
    assert download.status_code == 200
    assert download.data["download_url"] == "https://s3.example/download"


@pytest.mark.django_db
def test_runtime_capabilities_only_expose_configured_accelerators(settings):
    user = get_user_model().objects.create_user("capabilities@example.com", "password123")
    client = APIClient()
    client.force_authenticate(user)
    settings.TRAINING_BACKEND = "docker"
    settings.TRAINING_GPU_ENABLED = False
    settings.TRAINING_GPU_COUNTS = [1, 2]

    cpu_only = client.get("/api/training-jobs/runtime-capabilities/")

    assert cpu_only.status_code == 200
    assert cpu_only.data["enabled"] is True
    assert cpu_only.data["backend"] == "docker"
    assert cpu_only.data["accelerators"] == [{"type": "none", "counts": [0]}]

    settings.TRAINING_GPU_ENABLED = True
    with_gpu = client.get("/api/training-jobs/runtime-capabilities/")
    assert with_gpu.data["accelerators"][-1] == {"type": "gpu", "counts": [1, 2]}


@pytest.mark.django_db
def test_training_creation_and_submission_are_disabled_during_platform_validation(settings, monkeypatch):
    user = get_user_model().objects.create_user("training-disabled@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")
    job = TrainingJob.objects.create(
        project=project,
        name="queued-job",
        model_flavor="xgboost",
        code_snapshot_uri="s3://bucket/source.zip",
        data_snapshot_uri="s3://bucket/train.csv",
        output_uri="s3://bucket/model.tar.gz",
    )
    client = APIClient()
    client.force_authenticate(user)
    settings.TRAINING_ENABLED = False
    monkeypatch.setattr("apps.training.services.jobs.S3Storage", FakeStorage)

    capabilities = client.get("/api/training-jobs/runtime-capabilities/")
    create = client.post(
        "/api/training-jobs/",
        {
            "project": str(project.public_id),
            "name": "blocked",
            "model_flavor": "xgboost",
            "source_zip": SimpleUploadedFile("source.zip", b"zip", "application/zip"),
            "training_data": SimpleUploadedFile("train.csv", b"x\n1\n", "text/csv"),
        },
        format="multipart",
    )
    submit = client.post(f"/api/training-jobs/{job.public_id}/submit/")

    assert capabilities.status_code == 200
    assert capabilities.data == {
        "enabled": False,
        "backend": settings.TRAINING_BACKEND,
        "cpu_profiles": [],
        "accelerators": [],
    }
    assert create.status_code == 503
    assert submit.status_code == 503
    assert TrainingJob.objects.filter(public_id=job.public_id, status="pending").exists()


@pytest.mark.django_db
def test_training_job_list_reports_model_lifecycle_status():
    user = get_user_model().objects.create_user("model-status@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")

    def create_job(name, status="completed"):
        return TrainingJob.objects.create(
            project=project,
            name=name,
            model_flavor="sklearn",
            code_snapshot_uri=f"s3://bucket/{name}/source.zip",
            data_snapshot_uri=f"s3://bucket/{name}/data.csv",
            output_uri=f"s3://bucket/{name}/model.tar.gz",
            status=status,
        )

    not_trained = create_job("failed", status="failed")
    trained = create_job("trained")
    built = create_job("built")
    deployed = create_job("deployed")

    built_version = create_model_version(
        project,
        source_job=built,
        version="1",
        flavor="sklearn",
    )
    built_build = Build.objects.create(
        project=project,
        source_job=built,
        version=built_version,
        flavor="sklearn",
        status="ready",
    )
    deployed_version = create_model_version(
        project,
        source_job=deployed,
        version="2",
        flavor="sklearn",
    )
    deployed_build = Build.objects.create(
        project=project,
        source_job=deployed,
        version=deployed_version,
        flavor="sklearn",
        status="ready",
    )
    Deployment.objects.create(project=project, version=deployed_version, build=deployed_build, target="production", status="healthy")

    client = APIClient()
    client.force_authenticate(user)
    response = client.get("/api/training-jobs/")

    assert response.status_code == 200
    status_by_job = {item["id"]: item["model_status"] for item in response.data["results"]}
    assert status_by_job[str(not_trained.public_id)] == "none"
    assert status_by_job[str(trained.public_id)] == "trained"
    assert status_by_job[str(built.public_id)] == "built"
    assert status_by_job[str(deployed.public_id)] == "deployed"
    assert built_build.status == "ready"
