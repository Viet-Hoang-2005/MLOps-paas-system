from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import docker.errors
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor, DriftRun
from apps.registry.models import ModelVersion
from apps.training.models import TrainingJob
from apps.training.services.resources import validate_resources
from apps.observability.services import executions
from infrastructure.execution.job_containers import labels_for, start, observe


@pytest.fixture
def job(db, settings):
    settings.EXECUTION_WATCH_ENABLED = True
    owner = get_user_model().objects.create_user("p1-test@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="P1")
    return TrainingJob.objects.create(project=project, name="recovery", model_flavor="sklearn", backend="docker", status="queued")


def backend_mock(monkeypatch):
    backend = Mock(setting_name="")
    monkeypatch.setattr(executions, "backend_for", lambda row, kind: backend)
    return backend


def test_lost_enqueue_is_recoverable(job, monkeypatch):
    task = Mock()
    task.delay.side_effect = ConnectionError()
    executions.enqueue_safely(job, task)
    job.refresh_from_db()
    assert job.status == "queued" and job.observation_status == "retrying"
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "not_found"}
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.status == "running"
    backend.run.assert_called_once()


def test_lost_enqueue_preserves_cleanup_intent(job):
    job.status = "failed"
    job.observation_status = "cleanup_pending"
    job.execution_stop_requested = True
    job.save()
    task = Mock()
    task.delay.side_effect = ConnectionError()
    executions.enqueue_safely(job, task)
    job.refresh_from_db()
    assert job.status == "failed" and job.observation_status == "cleanup_pending"
    assert job.execution_stop_requested
    assert executions.claim("training", job.public_id)


def test_beat_enqueue_failure_preserves_cleanup_intent(job, monkeypatch):
    job.status = "failed"
    job.observation_status = "cleanup_pending"
    job.execution_stop_requested = True
    job.save()
    monkeypatch.setattr("apps.observability.tasks.reconcile_job_execution.apply_async", Mock(side_effect=ConnectionError()))
    assert executions.scan() == 0
    job.refresh_from_db()
    assert job.observation_status == "cleanup_pending" and job.execution_stop_requested
    assert job.execution_check_lease_until is None


def test_temporary_timeout_recovers_without_new_workload(job, monkeypatch):
    job.status = "running"
    job.save()
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "error", "error": "Docker timeout"}
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.status == "running" and job.observation_status == "retrying"
    backend.poll.return_value = {"status": "running", "started_at": timezone.now().isoformat()}
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.observation_status == "ok" and job.execution_deadline_at
    backend.run.assert_not_called()


def test_backend_connection_failure_is_an_observation_error(job, monkeypatch):
    monkeypatch.setattr(executions, "backend_for", Mock(side_effect=ConnectionError("Docker unavailable")))
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.status == "queued" and job.observation_status == "retrying"
    assert job.observation_error == "ConnectionError"


def test_dead_worker_lease_can_be_reclaimed_and_stale_result_ignored(job):
    first = executions.claim("training", job.public_id)[0][1]
    assert executions.claim("training", job.public_id) == []
    TrainingJob.objects.filter(pk=job.pk).update(execution_check_lease_until=timezone.now() - timedelta(seconds=1))
    second = executions.claim("training", job.public_id)[0][1]
    assert first != second
    assert executions.apply_observation("training", job.public_id, first, {"status": "failed"}) == "ignored"


def test_terminal_commit_precedes_cleanup(job, monkeypatch):
    job.status = "running"
    job.save()
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "completed"}
    monkeypatch.setattr(executions, "_completion_data", lambda row, kind: None)
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.status == "completed" and job.outputs.exists()
    backend.cleanup.assert_not_called()
    executions.reconcile("training", job.public_id)
    backend.cleanup.assert_called_once()
    job.refresh_from_db()
    assert job.observation_status == "ok"


def test_cleanup_recovers_timestamps_and_logs_before_runtime_removal(job, monkeypatch):
    job.status = "completed"
    job.completed_at = timezone.now()
    job.execution_stop_requested = True
    job.observation_status = "cleanup_pending"
    job.save()
    started = timezone.now() - timedelta(minutes=20)
    finished = started + timedelta(minutes=10)
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "completed", "runtime_id": "owned-runtime", "started_at": started.isoformat(), "finished_at": finished.isoformat(), "logs": "Training done"}

    def cleanup(row):
        saved = TrainingJob.objects.get(pk=job.pk)
        assert saved.status == "completed" and saved.runtime_seconds == 600
        assert saved.runtime_started_at == started and saved.tracking["logs_tail"] == "Training done"

    backend.cleanup.side_effect = cleanup
    executions.reconcile("training", job.public_id)
    backend.cleanup.assert_called_once()


def test_deadline_persists_cleanup_during_outage(job, monkeypatch):
    job.status = "running"
    job.runtime_started_at = timezone.now() - timedelta(hours=2)
    job.execution_deadline_at = timezone.now() - timedelta(seconds=1)
    job.save()
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "running"}
    backend.cleanup.side_effect = TimeoutError()
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.status == "failed" and job.execution_stop_requested
    assert job.observation_status == "cleanup_pending"
    backend.cleanup.side_effect = None
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.status == "failed" and job.observation_status == "ok"


def test_started_runtime_survives_dispatch_deadline_after_queue_loss(job, monkeypatch):
    start_time = timezone.now() - timedelta(minutes=35)
    job.dispatch_deadline_at = start_time + timedelta(minutes=30)
    job.max_runtime_seconds = 7200
    job.save()
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "running", "started_at": start_time.isoformat()}
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.status == "running" and job.runtime_started_at == start_time
    backend.run.assert_not_called()


def test_completed_before_runtime_deadline_recovers_after_long_outage(job, monkeypatch):
    start_time = timezone.now() - timedelta(hours=3)
    job.dispatch_deadline_at = start_time + timedelta(minutes=30)
    job.status = "running"
    job.save()
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "completed", "started_at": start_time.isoformat(), "finished_at": (start_time + timedelta(minutes=10)).isoformat()}
    monkeypatch.setattr(executions, "_completion_data", lambda row, kind: None)
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.status == "completed"
    assert job.runtime_seconds == 600


def test_created_container_is_started_after_worker_crash(job, monkeypatch):
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "created"}
    executions.reconcile("training", job.public_id)
    backend.run.assert_called_once()


def test_cancellation_wins_over_completion(job, monkeypatch):
    token = executions.claim("training", job.public_id)[0][1]
    TrainingJob.objects.filter(pk=job.pk).update(status="cancelling")
    monkeypatch.setattr(executions, "_completion_data", lambda row, kind: None)
    executions.apply_observation("training", job.public_id, token, {"status": "completed"})
    job.refresh_from_db()
    assert job.status == "cancelling" and not job.outputs.exists()


def test_observation_capability_resource_binding_and_replay(job):
    token = executions.claim("training", job.public_id)[0][1]
    auth = executions.signed_observation_token("training", job, token)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {auth}")
    wrong = client.post(f"/internal/executions/drift/{job.public_id}/observations/", {"status": "running"})
    assert wrong.status_code == 403
    url = f"/internal/executions/training/{job.public_id}/observations/"
    assert client.post(url, {"status": "running"}).status_code == 200
    assert client.post(url, {"status": "failed"}).status_code == 403


def test_recover_container_created_before_id_was_saved(job):
    container = Mock(id="existing", attrs={"Config": {"Labels": labels_for(job, "training")}, "State": {"Status": "running"}})
    docker_client = SimpleNamespace(run=Mock(), client=SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container))))
    assert start(docker_client, job, "training", image="unused") is container
    job.refresh_from_db()
    assert job.external_job_id == "existing"
    docker_client.run.assert_not_called()
    assert observe(docker_client.client, job, "training")["status"] == "running"


def test_wrong_ownership_never_adopted(job):
    container = Mock(attrs={"Config": {"Labels": {}}})
    client = SimpleNamespace(containers=SimpleNamespace(get=Mock(return_value=container)))
    assert observe(client, job, "training")["status"] == "error"
    container.remove.assert_not_called()


def test_terminal_deletion_request_remains_scannable(job):
    job.status = "completed"
    job.deletion_requested_at = timezone.now()
    job.save()
    assert executions.claim("training", job.public_id)


def test_delete_request_requires_runtime_cleanup_before_hard_delete(job, monkeypatch, django_capture_on_commit_callbacks):
    from apps.training.services.jobs import request_job_deletion
    from apps.training.tasks import delete_training_job
    job.status = "completed"
    job.save()
    monkeypatch.setattr("apps.training.services.jobs.cancel_training_job.delay", Mock(return_value=SimpleNamespace(id="test-task")))
    with django_capture_on_commit_callbacks(execute=True):
        request_job_deletion(job)
    job.refresh_from_db()
    assert job.observation_status == "cleanup_pending" and job.execution_stop_requested
    assert delete_training_job.run(str(job.public_id)) == "waiting-for-runtime-cleanup"


def test_stale_dispatch_cannot_create_a_runtime(job):
    token = executions.claim("training", job.public_id)[0][1]
    job.refresh_from_db()
    TrainingJob.objects.filter(pk=job.pk).update(execution_check_lease_until=timezone.now() - timedelta(seconds=1))
    docker_client = SimpleNamespace(run=Mock(), client=Mock())
    from common.api.exceptions import Conflict
    with pytest.raises(Conflict):
        start(docker_client, job, "training", image="unused")
    docker_client.run.assert_not_called()


def test_gpu_unavailable_fails_without_cpu_retry(job, monkeypatch, settings):
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = [1]
    job.accelerator_type, job.accelerator_count = "gpu", 1
    job.save()
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "not_found"}
    backend.run.side_effect = docker.errors.APIError("could not select device driver with capabilities: [[gpu]]")
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.status == "failed" and "GPU is unavailable" in job.error_message
    backend.run.assert_called_once()


def test_long_runtime_failure_is_persisted(job, monkeypatch):
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "failed", "error": "failure trace\n" * 1000}
    executions.reconcile("training", job.public_id)
    job.refresh_from_db()
    assert job.status == "failed" and len(job.error_message) == 12000


def test_drift_timeout_uses_same_recovery(job, monkeypatch):
    version = ModelVersion.objects.create(project=job.project, version="v1", flavor="sklearn")
    monitor = DriftMonitor.objects.create(version=version, name="monitor", backend="docker")
    run = DriftRun.objects.create(monitor=monitor, status="running", idempotency_key="p1-drift")
    backend = backend_mock(monkeypatch)
    backend.poll.return_value = {"status": "error", "error": "Docker timeout"}
    executions.reconcile("drift", run.public_id)
    run.refresh_from_db()
    assert run.status == "running" and run.observation_status == "retrying"


@pytest.mark.parametrize("values", [{"vcpu": 3}, {"memory_mb": 1024}, {"accelerator_count": 1}, {"max_runtime_seconds": 1}])
def test_invalid_resources_are_rejected(job, values):
    from rest_framework.exceptions import ValidationError
    with pytest.raises(ValidationError):
        validate_resources(values, job)
