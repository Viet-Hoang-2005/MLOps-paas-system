from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from infrastructure.execution.docker_backends import DockerTrainingBackend
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build
from apps.registry.models import ModelVersion
from apps.training.models import TrainingJob
from apps.training.services import jobs as job_service
from apps.training.tasks import delete_training_job, execute_training_job


def training_job(*, email="delete-training@example.com", status="completed"):
    owner = get_user_model().objects.create_user(email, "password123")
    project = ModelProject.objects.create(owner=owner, name=f"project-{email}")
    job = TrainingJob.objects.create(
        project=project,
        name="training",
        model_flavor="sklearn",
        code_snapshot_uri="s3://bucket/code.zip",
        data_snapshot_uri="s3://bucket/data.csv",
        output_uri="s3://bucket/output.tar.gz",
        status=status,
    )
    return owner, job


@pytest.mark.django_db
def test_delete_active_job_marks_cancelling_and_enqueues_once(
    monkeypatch, django_capture_on_commit_callbacks
):
    owner, job = training_job(status="running")
    client = APIClient()
    client.force_authenticate(owner)
    queued = []
    monkeypatch.setattr(
        job_service.cancel_training_job,
        "delay",
        lambda job_id: queued.append(job_id),
    )

    with django_capture_on_commit_callbacks(execute=True):
        first = client.delete(f"/api/training-jobs/{job.public_id}/")
        second = client.delete(f"/api/training-jobs/{job.public_id}/")

    assert first.status_code == 202
    assert second.status_code == 202
    job.refresh_from_db()
    assert job.status == "cancelling"
    assert job.deletion_requested_at is not None
    assert queued == [str(job.public_id)]


@pytest.mark.django_db
def test_delete_terminal_job_enqueues_cleanup_and_tenant_isolation(
    monkeypatch, django_capture_on_commit_callbacks
):
    owner, job = training_job()
    stranger = get_user_model().objects.create_user("stranger@example.com", "password123")
    client = APIClient()
    client.force_authenticate(stranger)
    assert client.delete(f"/api/training-jobs/{job.public_id}/").status_code == 404

    queued = []
    monkeypatch.setattr(
        job_service.delete_training_job,
        "delay",
        lambda job_id: queued.append(job_id),
    )
    client.force_authenticate(owner)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete(f"/api/training-jobs/{job.public_id}/")

    assert response.status_code == 202
    assert response.data["deletion_pending"] is True
    assert queued == [str(job.public_id)]


@pytest.mark.django_db
def test_delete_is_blocked_by_active_model_build():
    owner, job = training_job()
    Build.objects.create(
        project=job.project,
        source_job=job,
        source_job_reference=job.public_id,
        flavor="sklearn",
        status="building",
    )
    client = APIClient()
    client.force_authenticate(owner)

    response = client.delete(f"/api/training-jobs/{job.public_id}/")

    assert response.status_code == 409
    job.refresh_from_db()
    assert job.deletion_requested_at is None


@pytest.mark.django_db
def test_hard_delete_preserves_registered_version_and_ready_image(monkeypatch):
    _, job = training_job()
    version = ModelVersion.objects.create(
        project=job.project,
        source_job=job,
        source_job_reference=job.public_id,
        version="1",
    )
    build = Build.objects.create(
        project=job.project,
        source_job=job,
        source_job_reference=job.public_id,
        version=version,
        flavor="sklearn",
        status="ready",
        image_uri=f"image-{job.project.public_id}:v1",
    )
    TrainingJob.objects.filter(pk=job.pk).update(deletion_requested_at=timezone.now())
    storage = SimpleNamespace(delete_prefix=lambda _prefix: None)
    monkeypatch.setattr("apps.training.tasks.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.training.services.logs.delete_training_logs", lambda _job_id: None)

    assert delete_training_job.run(str(job.public_id)) == "deleted"

    assert not TrainingJob.objects.filter(pk=job.pk).exists()
    build.refresh_from_db()
    version.refresh_from_db()
    assert build.source_job is None
    assert version.source_job is None
    assert build.source_job_reference == job.public_id
    assert version.source_job_reference == job.public_id
    assert build.image_uri.endswith(":v1")


@pytest.mark.django_db
def test_execute_failure_does_not_overwrite_cancelling(monkeypatch):
    _, job = training_job(status="queued")

    class Backend:
        def run(self, selected_job):
            TrainingJob.objects.filter(pk=selected_job.pk).update(status="cancelling")
            raise RuntimeError("container stopped")

    monkeypatch.setattr("apps.training.tasks.training_backend", lambda _backend: Backend())
    monkeypatch.setattr("apps.training.services.logs.append_training_log", lambda *_args: None)

    assert execute_training_job.run(str(job.public_id)) == "cancelling"
    job.refresh_from_db()
    assert job.status == "cancelling"


def test_docker_cancel_waits_for_exit_and_removes_container():
    calls = []

    class Container:
        def kill(self):
            calls.append("kill")

        def wait(self, timeout):
            calls.append(("wait", timeout))

        def remove(self, force):
            calls.append(("remove", force))

    docker_client = SimpleNamespace(
        client=SimpleNamespace(containers=SimpleNamespace(get=lambda _container_id: Container()))
    )
    backend = DockerTrainingBackend(docker_client=docker_client, storage=SimpleNamespace())

    result = backend.cancel(SimpleNamespace(external_job_id="container-id"))

    assert result == {"dispatched": False, "confirmed": True}
    assert calls == ["kill", ("wait", 30), ("remove", True)]


def test_docker_cancel_retries_when_execution_started_before_container_registration():
    backend = DockerTrainingBackend(
        docker_client=SimpleNamespace(client=SimpleNamespace()),
        storage=SimpleNamespace(),
    )

    result = backend.cancel(
        SimpleNamespace(
            started_at=timezone.now(),
            external_job_id="",
        )
    )

    assert result["confirmed"] is False
    assert result["retry"] is True
