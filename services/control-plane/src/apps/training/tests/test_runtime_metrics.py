import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob
from apps.training.services import local_gpu
from apps.training.services import runtime_metrics as metrics
from infrastructure.execution.job_containers import labels_for

GPU = "GPU-01234567-89ab-cdef-0123-456789abcdef"


@pytest.fixture
def job(db):
    owner = get_user_model().objects.create_user("runtime@example.com")
    project = ModelProject.objects.create(owner=owner, name="Runtime")
    return TrainingJob.objects.create(
        project=project,
        model_flavor="pytorch",
        status="running",
        backend="docker",
        external_job_id="container-1",
        vcpu=2,
        memory_mb=4096,
        max_runtime_seconds=3600,
        input_contract="legacy",
        submitted_at=timezone.now(),
    )


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def test_docker_exact_owned_container_and_partial_gpu(job, monkeypatch):
    job.accelerator_type = "gpu"
    job.local_gpu_id = GPU
    container = Mock(id="container-1")
    container.attrs = {"Config": {"Labels": labels_for(job, "training")}, "State": {"Status": "running"}}
    container.stats.return_value = {
        "cpu_stats": {"cpu_usage": {"total_usage": 60}, "system_cpu_usage": 200, "online_cpus": 4},
        "precpu_stats": {"cpu_usage": {"total_usage": 10}, "system_cpu_usage": 100},
        "memory_stats": {"usage": 120 * 1048576, "stats": {"inactive_file": 20 * 1048576}},
    }
    client = Mock()
    client.containers.get.return_value = container
    monkeypatch.setattr(metrics.docker, "from_env", lambda **kwargs: client)
    monkeypatch.setattr(
        local_gpu,
        "device_metrics",
        lambda gpu: {"gpu_percent": 20, "gpu_memory_used_mb": 1000, "gpu_memory_total_mb": 4000},
    )
    point = metrics._docker_snapshot(job)
    assert point["cpu_percent"] == 100
    assert point["memory_used_mb"] == 100
    assert point["gpu_percent"] == 20 and point["gpu_memory_percent"] == 25
    client.containers.get.assert_called_once_with(f"training-{job.public_id}")
    client.close.assert_called_once()
    container.attrs["Config"]["Labels"]["mlops_tenant_id"] = "wrong"
    assert metrics._docker_snapshot(job) is None
    container.attrs["Config"]["Labels"] = labels_for(job, "training")
    container.id = "other"
    assert metrics._docker_snapshot(job) is None


def test_gpu_failure_preserves_docker_cpu_and_ram(job, monkeypatch):
    job.accelerator_type, job.local_gpu_id = "gpu", GPU
    container = Mock(id="container-1")
    container.attrs = {"Config": {"Labels": labels_for(job, "training")}, "State": {"Status": "running"}}
    container.stats.return_value = {"memory_stats": {"usage": 1048576, "stats": {}}}
    client = Mock()
    client.containers.get.return_value = container
    monkeypatch.setattr(metrics.docker, "from_env", lambda **kwargs: client)
    monkeypatch.setattr(local_gpu, "device_metrics", lambda _: None)
    point = metrics._docker_snapshot(job)
    assert point["cpu_percent"] is None and point["memory_used_mb"] == 1 and point["gpu_percent"] is None


def vector(value, **labels):
    return [{"metric": labels, "value": [time.time(), str(value)]}]


def test_prometheus_scopes_all_metrics_to_owned_pod(job):
    job.backend, job.accelerator_type = "argo", "gpu"
    labels = {"namespace": "mlops-paas-training", "pod": "owned", "container": "node"}
    gpu = {**labels, "UUID": GPU}
    client = Mock(enabled=True)
    client.query.side_effect = [
        vector(1, namespace=labels["namespace"], pod="owned"),
        vector(1, **labels),
        vector(1024 * 1048576, **labels),
        vector(40, **gpu),
        vector(1024, **gpu),
        vector(3000, **gpu),
        vector(72, **gpu),
    ]
    point = metrics._prometheus_snapshot(job, client)
    assert point["cpu_percent"] == 50 and point["memory_percent"] == 25
    assert point["gpu_percent"] == 40 and point["gpu_memory_percent"] == 25
    query = client.query.call_args_list[0].args[0]
    assert (
        str(job.public_id) in query
        and str(job.project.public_id) in query
        and str(job.project.owner.tenant_id) in query
    )
    assert all('pod="owned"' in c.args[0] for c in client.query.call_args_list[1:])


def test_prometheus_rejects_ambiguous_gpu_and_keeps_cpu(job):
    job.backend, job.accelerator_type = "argo", "gpu"
    labels = {"namespace": "mlops-paas-training", "pod": "owned", "container": "node"}
    client = Mock(enabled=True)
    client.query.side_effect = [
        vector(1, namespace=labels["namespace"], pod="owned"),
        vector(1, **labels),
        vector(100, **labels),
        vector(10, **{**labels, "UUID": GPU}) * 2,
    ]
    point = metrics._prometheus_snapshot(job, client)
    assert point["cpu_percent"] == 50 and point["gpu_percent"] is None


def test_prometheus_stale_and_invalid_values():
    client = Mock()
    client.query.return_value = [{"metric": {}, "value": [time.time() - 91, "5"]}]
    assert metrics._vector(client, "query") is None
    client.query.return_value = vector("NaN")
    assert metrics._vector(client, "query") is None


def test_prometheus_missing_reserved_memory_does_not_guess_total(job):
    job.backend, job.accelerator_type = "argo", "gpu"
    labels = {"namespace": "mlops-paas-training", "pod": "owned", "container": "node"}
    gpu = {**labels, "UUID": GPU}
    client = Mock(enabled=True)
    client.query.side_effect = [
        vector(1, namespace=labels["namespace"], pod="owned"),
        vector(1, **labels),
        vector(100, **labels),
        vector(40, **gpu),
        vector(1024, **gpu),
        vector(3072, **gpu),
        [],
    ]
    point = metrics._prometheus_snapshot(job, client)
    assert point["gpu_percent"] == 40 and point["gpu_memory_used_mb"] == 1024
    assert point["gpu_memory_total_mb"] is None and point["gpu_memory_percent"] is None


def test_runtime_failure_returns_sanitized_unavailable(job, monkeypatch):
    monkeypatch.setattr(metrics, "_docker_snapshot", Mock(side_effect=RuntimeError("private socket")))
    response = metrics.runtime_metrics(job)
    assert response["status"] == "unavailable" and response["latest"] is None
    assert "private socket" not in str(response)


def test_cache_coalesces_requests_and_terminal_jobs_hide_metrics(job, monkeypatch):
    entered, finish = Event(), Event()

    def sample(_job):
        entered.set()
        assert finish.wait(5)
        return {**metrics._point(job), "cpu_percent": 50}

    monkeypatch.setattr(metrics, "_docker_snapshot", sample)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(metrics.runtime_metrics, job)
        assert entered.wait(5)
        assert metrics.runtime_metrics(job)["status"] == "waiting"
        finish.set()
        assert first.result()["status"] == "available"
    assert metrics.runtime_metrics(job)["latest"]["cpu_percent"] == 50
    job.status = "completed"
    assert metrics.runtime_metrics(job)["latest"] is None


@pytest.mark.django_db
def test_endpoint_requires_owner_and_does_not_accept_runtime_input(job, monkeypatch):
    client = APIClient()
    url = f"/api/training-jobs/{job.public_id}/runtime-metrics/"
    assert client.get(url).status_code == 401
    other = get_user_model().objects.create_user("other-runtime@example.com")
    client.force_authenticate(other)
    assert client.get(url).status_code == 404
    client.force_authenticate(job.project.owner)
    sample = Mock(return_value={"status": "waiting"})
    monkeypatch.setattr("apps.training.api.metrics_endpoints.runtime_metrics", sample)
    assert client.get(url, {"pod": "another"}).status_code == 200
    assert sample.call_args.args[0].public_id == job.public_id
