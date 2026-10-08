import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment
from apps.registry.models import ModelVersion
from apps.training.models import TrainingJob


@pytest.mark.django_db
def test_training_job_paths_are_project_scoped(monkeypatch):
    user = get_user_model().objects.create_user("owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(
        "/api/training-jobs/",
        {
            "project": str(project.public_id),
            "name": "nightly",
            "model_flavor": "xgboost",
            "requirements_text": "xgboost==2.0.3",
            "code_snapshot_uri": "s3://other-tenant/source.zip",
            "data_snapshot_uri": "s3://other-tenant/train.csv",
        },
        format="json",
    )

    assert response.status_code == 201
    job = TrainingJob.objects.get(public_id=response.data["id"])
    prefix = f"users/{user.tenant_id}/models/{project.public_id}/training/jobs/{job.public_id}"
    assert job.code_snapshot_uri.endswith(f"{prefix}/input/code/source.zip")
    assert job.data_snapshot_uri.endswith(f"{prefix}/input/data/data.zip")
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
def test_training_creation_and_submission_are_disabled_during_platform_validation(settings):
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

    capabilities = client.get("/api/training-jobs/runtime-capabilities/")
    create = client.post(
        "/api/training-jobs/",
        {"project": str(project.public_id), "name": "blocked", "model_flavor": "xgboost"},
        format="json",
    )
    submit = client.post(f"/api/training-jobs/{job.public_id}/submit/")

    assert capabilities.status_code == 200
    assert capabilities.data == {
        "enabled": False,
        "backend": settings.TRAINING_BACKEND,
        "cpu_profiles": [],
        "runtime_options_seconds": [],
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
def test_submit_job_requires_pending_status(monkeypatch):
    user = get_user_model().objects.create_user("submit-status@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")
    client = APIClient()
    client.force_authenticate(user)
    monkeypatch.setattr("apps.observability.services.outbox._publish_pending", lambda: None)

    pending_job = TrainingJob.objects.create(
        project=project,
        name="pending-job",
        model_flavor="sklearn",
        code_snapshot_uri="s3://bucket/source.zip",
        data_snapshot_uri="s3://bucket/train.csv",
        output_uri="s3://bucket/model.tar.gz",
        status="pending",
    )
    submit_res = client.post(f"/api/training-jobs/{pending_job.public_id}/submit/")
    assert submit_res.status_code == 202
    pending_job.refresh_from_db()
    assert pending_job.status == "queued"

    # Submitting already queued job fails with 409 Conflict
    re_submit = client.post(f"/api/training-jobs/{pending_job.public_id}/submit/")
    assert re_submit.status_code == 409
    assert "Only pending jobs can be submitted" in re_submit.data["error"]["detail"]

    # Submitting a failed job fails with 409 Conflict
    failed_job = TrainingJob.objects.create(
        project=project,
        name="failed-job",
        model_flavor="sklearn",
        code_snapshot_uri="s3://bucket/source.zip",
        data_snapshot_uri="s3://bucket/train.csv",
        output_uri="s3://bucket/model.tar.gz",
        status="failed",
    )
    failed_submit = client.post(f"/api/training-jobs/{failed_job.public_id}/submit/")
    assert failed_submit.status_code == 409
    assert "Only pending jobs can be submitted" in failed_submit.data["error"]["detail"]

    # Submitting a cancelled job fails with 409 Conflict
    cancelled_job = TrainingJob.objects.create(
        project=project,
        name="cancelled-job",
        model_flavor="sklearn",
        code_snapshot_uri="s3://bucket/source.zip",
        data_snapshot_uri="s3://bucket/train.csv",
        output_uri="s3://bucket/model.tar.gz",
        status="cancelled",
    )
    cancelled_submit = client.post(f"/api/training-jobs/{cancelled_job.public_id}/submit/")
    assert cancelled_submit.status_code == 409
    assert "Only pending jobs can be submitted" in cancelled_submit.data["error"]["detail"]


@pytest.mark.django_db
def test_failed_job_retry_endpoint_creates_new_attempt(monkeypatch):
    from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
    from django.core.files.uploadedfile import SimpleUploadedFile

    user = get_user_model().objects.create_user("retry-endpoint@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")
    client = APIClient()
    client.force_authenticate(user)
    monkeypatch.setattr("apps.observability.services.outbox._publish_pending", lambda: None)

    storage = MemoryStorage()
    code_file = storage.put("orig/code.zip", SimpleUploadedFile("code.zip", b"code"), "application/zip")
    data_file = storage.put("orig/data.zip", SimpleUploadedFile("data.zip", b"data"), "application/zip")

    failed_job = TrainingJob.objects.create(
        project=project,
        name="failed-job",
        model_flavor="sklearn",
        code_snapshot_uri=code_file.uri,
        data_snapshot_uri=data_file.uri,
        output_uri="s3://bucket/model.tar.gz",
        status="failed",
    )

    monkeypatch.setattr("apps.training.services.jobs.S3Storage", lambda: storage)
    retry_res = client.post(f"/api/training-jobs/{failed_job.public_id}/retry/")
    assert retry_res.status_code == 201

    failed_job.refresh_from_db()
    assert failed_job.status == "failed"

    new_job = TrainingJob.objects.get(public_id=retry_res.data["id"])
    assert new_job.pk != failed_job.pk
    assert new_job.public_id != failed_job.public_id
    assert new_job.retry_of == failed_job
    assert new_job.status == "queued"
    assert new_job.trigger_kind == "retry"


