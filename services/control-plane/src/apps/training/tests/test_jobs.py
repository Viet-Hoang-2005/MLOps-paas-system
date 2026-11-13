import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.training.tests.factories import training_job
from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment
from apps.registry.models import ModelVersion

from .test_job_drafts import studio as studio


@pytest.mark.django_db
def test_runtime_capabilities_only_expose_configured_accelerators(settings, monkeypatch):
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
    monkeypatch.setattr(
        "apps.training.services.local_gpu.inventory",
        lambda **kwargs: {
            "status": "available",
            "reason": "",
            "devices": [{"id": "GPU-01234567-89ab-cdef-0123-456789abcdef"}],
        },
    )
    with_gpu = client.get("/api/training-jobs/runtime-capabilities/")
    assert with_gpu.data["accelerators"][-1] == {
        "type": "gpu",
        "model": "",
        "counts": [1],
        "device_id": "GPU-01234567-89ab-cdef-0123-456789abcdef",
    }


@pytest.mark.django_db
def test_editing_is_available_while_submission_is_disabled(studio, settings):
    job, _, client, _ = studio
    settings.TRAINING_ENABLED = False
    assert client.get("/api/training-jobs/runtime-capabilities/").data["enabled"] is False
    assert client.post("/api/training-workspaces/", {}, format="json").status_code == 201
    assert (
        client.post(
            f"/api/training-workspaces/{job.public_id}/runs/",
            {"revision": job.revision, "run_key": str(__import__("uuid").uuid4())},
            format="json",
        ).status_code
        == 503
    )
    job.refresh_from_db()
    assert job.status == "ready"


@pytest.mark.django_db
def test_training_job_list_reports_model_lifecycle_status():
    user = get_user_model().objects.create_user("model-status@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")

    def create_job(name, status="completed"):
        return training_job(
            project=project,
            model_flavor="sklearn",
            code_snapshot_uri=f"s3://bucket/{name}/source.zip",
            data_snapshot_uri=f"s3://bucket/{name}/data.csv",
            output_uri=f"s3://bucket/{name}/model.tar.gz",
            status=status,
            vcpu=2,
            memory_mb=4096,
            max_runtime_seconds=3600,
            input_contract="legacy",
            submitted_at=timezone.now(),
        )

    not_trained = create_job("failed", status="failed")
    trained = create_job("trained")
    built = create_job("built")
    deployed = create_job("deployed")

    built_version = ModelVersion.objects.create(
        project=project,
        source_job=built,
        source_job_reference=built.public_id,
        version="1",
        flavor="sklearn",
    )
    built_build = Build.objects.create(
        project=project,
        source_job=built,
        source_job_reference=built.public_id,
        version=built_version,
        flavor="sklearn",
        status="ready",
    )
    deployed_version = ModelVersion.objects.create(
        project=project,
        source_job=deployed,
        source_job_reference=deployed.public_id,
        version="2",
        flavor="sklearn",
    )
    deployed_build = Build.objects.create(
        project=project,
        source_job=deployed,
        source_job_reference=deployed.public_id,
        version=deployed_version,
        flavor="sklearn",
        status="ready",
    )
    project.active_deployment = Deployment.objects.create(
        version=deployed_version, build=deployed_build, status="succeeded"
    )
    project.save(update_fields=["active_deployment"])

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


@pytest.mark.django_db
def test_submit_job_is_idempotent_for_one_run_key(studio, monkeypatch):
    import uuid

    job, storage, client, _ = studio
    monkeypatch.setattr("apps.training.services.drafts.S3Storage", lambda: storage)
    payload = {"revision": job.revision, "run_key": str(uuid.uuid4())}
    url = f"/api/training-workspaces/{job.public_id}/runs/"
    assert client.post(url, payload, format="json").status_code == 201
    assert client.post(url, payload, format="json").status_code == 201
    assert client.post(url, {**payload, "run_key": str(uuid.uuid4())}, format="json").status_code == 409
    job.refresh_from_db()
    assert job.jobs.get().status == "queued"
