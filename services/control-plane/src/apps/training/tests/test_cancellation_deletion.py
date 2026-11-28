from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build
from apps.registry.models import ModelVersion
from apps.training.jobs import lifecycle as job_service
from apps.training.jobs.models import TrainingJob
from apps.training.jobs.tasks import delete_training_job, execute_training_job
from apps.training.tests.factories import training_job as make_training_job
from infrastructure.execution.training import DockerTrainingBackend
from infrastructure.images.references import temporary_image_reference
from infrastructure.storage.paths import build_prefix


def training_job(*, email="delete-training@example.com", status="completed"):
    owner = get_user_model().objects.create_user(email, "password123")
    project = ModelProject.objects.create(owner=owner, name=f"project-{email}")
    job = make_training_job(
        project=project,
        model_flavor="sklearn",
        code_snapshot_uri="s3://bucket/code.zip",
        data_snapshot_uri="s3://bucket/data.csv",
        output_uri="s3://bucket/output.tar.gz",
        status=status,
        vcpu=2,
        memory_mb=4096,
        max_runtime_seconds=3600,
        input_contract="legacy",
        submitted_at=timezone.now(),
    )
    return owner, job


@pytest.mark.django_db
def test_delete_active_job_marks_cancelling_and_enqueues_once(monkeypatch, django_capture_on_commit_callbacks):
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
def test_delete_terminal_job_enqueues_cleanup_and_tenant_isolation(monkeypatch, django_capture_on_commit_callbacks):
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
@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_delete_job_quiesces_and_cleans_terminal_builds(monkeypatch, django_capture_on_commit_callbacks, status):
    owner, job = training_job()
    failed_build = Build.objects.create(
        project=job.project,
        source_job=job,
        source_job_reference=job.public_id,
        flavor="sklearn",
        status=status,
        backend="docker",
        next_execution_check_at=timezone.now(),
    )
    client = APIClient()
    client.force_authenticate(owner)
    monkeypatch.setattr(job_service.delete_training_job, "delay", lambda _id: SimpleNamespace(id="task-1"))

    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete(f"/api/training-jobs/{job.public_id}/")

    assert response.status_code == 202
    storage = Mock()
    runtime_stop = Mock(side_effect=RuntimeError("runner still active"))
    image_cleanup = Mock()
    delete_logs = Mock()
    monkeypatch.setattr("apps.training.jobs.tasks.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.deployment.builds.cleanup.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.deployment.builds.cleanup.stop_build_for_deletion", runtime_stop)
    monkeypatch.setattr("apps.deployment.builds.cleanup.BuildImageCleaner", lambda: image_cleanup)
    monkeypatch.setattr("apps.training.jobs.logs.delete_training_logs", delete_logs)

    with pytest.raises(RuntimeError, match="runner still active"):
        delete_training_job.run(str(job.public_id))
    failed_build.refresh_from_db()
    assert failed_build.deletion_state == "delete_failed"
    job.refresh_from_db()
    assert job.deletion_error == "runner still active"
    storage.delete_prefix.assert_not_called()
    image_cleanup.delete.assert_not_called()
    delete_logs.assert_not_called()

    runtime_stop.side_effect = None
    prefix = f"{build_prefix(owner.tenant_id, job.project.public_id, failed_build.public_id).rstrip('/')}/"
    assert delete_training_job.run(str(job.public_id)) == "deleted"
    assert storage.delete_prefix.call_args_list[0].args == (prefix,)
    assert storage.delete_prefix.call_count == 2
    assert image_cleanup.delete.call_args.args[0].image_uri == temporary_image_reference(
        job.project.public_id, failed_build.public_id
    )
    delete_logs.assert_called_once_with(job.public_id)
    assert not TrainingJob.objects.filter(pk=job.pk).exists()
    assert not Build.objects.filter(pk=failed_build.pk).exists()


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
    monkeypatch.setattr("apps.training.jobs.tasks.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.training.jobs.logs.delete_training_logs", lambda _job_id: None)

    assert delete_training_job.run(str(job.public_id)) == "blocked-by-build"

    assert TrainingJob.objects.filter(pk=job.pk).exists()
    build.refresh_from_db()
    version.refresh_from_db()
    assert build.source_job_id == job.pk
    assert version.source_job_id == job.pk
    assert build.source_job_reference == job.public_id
    assert version.source_job_reference == job.public_id
    assert build.image_uri.endswith(":v1")


@pytest.mark.django_db
def test_execute_failure_does_not_overwrite_cancelling(monkeypatch):
    from contextlib import nullcontext

    _, job = training_job(status="queued")
    TrainingJob.objects.filter(pk=job.pk).update(
        submitted_at=timezone.now(),
        observation_status="ok",
        next_execution_check_at=timezone.now(),
    )

    class Backend:
        docker = SimpleNamespace(client=None)

        def poll(self, selected_job):
            return {"status": "not_found"}

        def run(self, selected_job):
            TrainingJob.objects.filter(pk=selected_job.pk).update(status="cancelling")
            raise RuntimeError("container stopped")

        def cleanup(self, selected_job):
            return {"confirmed": True}

    monkeypatch.setattr("apps.observability.execution.reconciliation.backend_for", lambda *_args: Backend())
    monkeypatch.setattr("apps.training.resources.local_capacity.dispatch_guard", lambda *_args: nullcontext())
    monkeypatch.setattr("apps.training.jobs.logs.append_training_log", lambda *_args: None)

    assert execute_training_job.run(str(job.public_id)) == "cancelling"
    job.refresh_from_db()
    assert job.status == "cancelling"


@pytest.mark.django_db
def test_docker_cancel_waits_for_exit_and_removes_container():
    from infrastructure.execution.job_containers import labels_for

    _, job = training_job(status="running")
    job.external_job_id = "container-id"
    calls = []

    class Container:
        id = "container-id"
        attrs = {"Config": {"Labels": labels_for(job, "training")}, "State": {"Status": "running"}}

        def reload(self):
            pass

        def stop(self, timeout):
            calls.append(("stop", timeout))

        def remove(self, force):
            calls.append(("remove", force))

    docker_client = SimpleNamespace(
        client=SimpleNamespace(containers=SimpleNamespace(get=lambda _container_id: Container()))
    )
    backend = DockerTrainingBackend(docker_client=docker_client, storage=SimpleNamespace())

    result = backend.cancel(job)

    assert result == {"dispatched": False, "confirmed": True}
    assert calls == [("stop", 30), ("remove", True)]


@pytest.mark.django_db
def test_docker_cancel_adopts_runtime_before_container_registration():
    from infrastructure.execution.job_containers import labels_for

    _, job = training_job(status="running")
    container = Mock(
        id="unregistered", attrs={"Config": {"Labels": labels_for(job, "training")}, "State": {"Status": "running"}}
    )
    backend = DockerTrainingBackend(
        docker_client=SimpleNamespace(
            client=SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container)))
        ),
        storage=SimpleNamespace(),
    )

    result = backend.cancel(job)

    assert result["confirmed"] is True
    container.stop.assert_called_once_with(timeout=30)
    container.remove.assert_called_once_with(force=True)
