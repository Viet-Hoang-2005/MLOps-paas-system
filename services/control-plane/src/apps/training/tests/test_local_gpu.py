from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import docker
import pytest
import requests
from django.core.cache import cache
from rest_framework.exceptions import ValidationError

from apps.training.services import local_gpu

GPU = "GPU-01234567-89ab-cdef-0123-456789abcdef"
OTHER = "GPU-11234567-89ab-cdef-0123-456789abcdef"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def docker_client(output=None):
    container = Mock()
    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = (output or f"{GPU}, NVIDIA Test, 8192, 6144\n").encode()
    client = Mock()
    client.containers.list.return_value = []
    client.containers.create.return_value = container
    return client, container


def test_probe_discovers_nvidia_without_network_or_credentials():
    client, container = docker_client()
    result = local_gpu._probe(client=client)
    assert result["devices"] == [{"id": GPU, "name": "NVIDIA Test", "memory_total_mib": 8192, "memory_free_mib": 6144}]
    kwargs = client.containers.create.call_args.kwargs
    assert kwargs["network_disabled"] is True
    assert "environment" not in kwargs and "volumes" not in kwargs
    assert kwargs["device_requests"][0]["Count"] == -1
    client.images.get.assert_called_once_with(local_gpu.IMAGE)
    client.images.pull.assert_not_called()
    container.remove.assert_called_once_with(force=True)


def test_probe_reads_multiple_gpus_and_unknown_free_memory():
    client, _ = docker_client(f"{GPU}, NVIDIA One, 8192, N/A\n{OTHER}, NVIDIA Two, 24576, 20000\n")
    devices = local_gpu._probe(client=client)["devices"]
    assert [device["id"] for device in devices] == [GPU, OTHER]
    assert devices[0]["memory_free_mib"] is None
    assert devices[1]["memory_total_mib"] == 24576


@pytest.mark.parametrize("error,status,reason", [
    (docker.errors.ImageNotFound("missing"), "unavailable", "image_missing"),
    (docker.errors.APIError("no gpu"), "unavailable", "nvidia_unavailable"),
    (requests.Timeout("timeout"), "error", "docker_unavailable"),
])
def test_probe_failures_are_bounded_and_do_not_pull(error, status, reason):
    client, _ = docker_client()
    client.images.get.side_effect = error
    result = local_gpu._probe(client=client)
    assert (result["status"], result["reason"]) == (status, reason)
    client.images.pull.assert_not_called()


def test_probe_removes_container_after_wait_timeout():
    client, container = docker_client()
    container.wait.side_effect = requests.Timeout("timeout")
    assert local_gpu._probe(client=client)["status"] == "error"
    container.remove.assert_called_once_with(force=True)


def test_next_probe_reaps_only_own_expired_probes():
    client, _ = docker_client()
    expired = Mock(name=local_gpu.PROBE_PREFIX + "a" * 32)
    expired.name = local_gpu.PROBE_PREFIX + "a" * 32
    expired.attrs = {"Config": {"Labels": {"mlops_paas.gpu_probe_expires": "1"}}}
    unrelated = Mock()
    unrelated.name = "another-container"
    unrelated.attrs = expired.attrs
    client.containers.list.return_value = [expired, unrelated]
    assert local_gpu._probe(client=client)["status"] == "available"
    expired.remove.assert_called_once_with(force=True)
    unrelated.remove.assert_not_called()


def test_selected_probe_requires_exactly_requested_gpu():
    client, container = docker_client()
    assert local_gpu.require_device(GPU, client=client)["id"] == GPU
    assert client.containers.create.call_args.kwargs["device_requests"][0]["DeviceIDs"] == [GPU]
    container.logs.return_value = f"{OTHER}, NVIDIA Other, 8192, 4096\n".encode()
    with pytest.raises(ValidationError):
        local_gpu.require_device(GPU, client=client)
    with pytest.raises(ValidationError):
        local_gpu.require_device("not-a-uuid", client=client)


def test_inventory_cached_and_force_refresh(monkeypatch):
    probe = Mock(side_effect=[local_gpu._result("available", devices=[{"id": GPU}]),
                              local_gpu._result("unavailable", "nvidia_unavailable")])
    monkeypatch.setattr(local_gpu, "_probe", probe)
    assert local_gpu.inventory()["status"] == "available"
    assert local_gpu.inventory()["status"] == "available"
    assert local_gpu.inventory(force=True)["status"] == "unavailable"
    assert probe.call_count == 2


def test_concurrent_inventory_only_starts_one_probe(monkeypatch):
    started, release = Event(), Event()

    def probe():
        started.set()
        assert release.wait(5)
        return local_gpu._result("available", devices=[{"id": GPU}])

    monkeypatch.setattr(local_gpu, "_probe", probe)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(local_gpu.inventory)
        try:
            assert started.wait(5)
            assert workers.submit(local_gpu.inventory).result(timeout=5)["status"] == "checking"
        finally:
            release.set()
        assert first.result(timeout=5)["status"] == "available"


def test_selected_device_check_respects_shared_probe_lock(monkeypatch):
    from common.api.exceptions import ServiceUnavailable

    started, release = Event(), Event()
    def probe():
        started.set()
        assert release.wait(5)
        return local_gpu._result("available", devices=[{"id": GPU}])

    monkeypatch.setattr(local_gpu, "_probe", probe)
    with ThreadPoolExecutor(max_workers=1) as workers:
        future = workers.submit(local_gpu.inventory)
        try:
            assert started.wait(5)
            with pytest.raises(ServiceUnavailable):
                local_gpu.require_device(GPU)
        finally:
            release.set()
        assert future.result(timeout=5)["status"] == "available"


@pytest.mark.django_db
def test_capabilities_keep_cpu_when_docker_unavailable(settings, monkeypatch):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    settings.TRAINING_BACKEND = "docker"
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = (1,)
    probe = Mock(return_value=local_gpu._result("error", "docker_unavailable"))
    monkeypatch.setattr(local_gpu, "inventory", probe)
    client = APIClient()
    client.force_authenticate(get_user_model().objects.create_user("gpu-capability-test@example.com"))
    response = client.get("/api/training-jobs/runtime-capabilities/?refresh=1")
    assert response.status_code == 200
    assert response.data["accelerators"] == [{"type": "none", "counts": [0]}]
    assert response.data["local_gpu"]["reason"] == "docker_unavailable"
    probe.assert_called_once_with(force=True)


@pytest.mark.django_db
def test_submit_checks_selected_device_before_queuing(settings, monkeypatch):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.catalog.models import ModelProject
    from apps.training.models import TrainingJob

    settings.TRAINING_BACKEND = "docker"
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = (1,)
    user = get_user_model().objects.create_user("gpu-submit-test@example.com")
    project = ModelProject.objects.create(owner=user, name="gpu project")
    job = TrainingJob.objects.create(project=project, name="gpu", model_flavor="pytorch",
        accelerator_type="gpu", accelerator_count=1, local_gpu_id=GPU)
    check = Mock(side_effect=ValidationError({"local_gpu_id": "Selected GPU is unavailable."}))
    monkeypatch.setattr(local_gpu, "require_device", check)
    client = APIClient()
    client.force_authenticate(user)
    response = client.post(f"/api/training-jobs/{job.public_id}/submit/")
    assert response.status_code == 400
    assert TrainingJob.objects.get(pk=job.pk).status == "pending"
    check.assert_called_once_with(GPU)


@pytest.mark.parametrize("backend,kind,device_id", [
    ("docker", "gpu", ""),
    ("docker", "gpu", "bad-input"),
    ("docker", "none", GPU),
    ("argo", "gpu", GPU),
])
def test_rejects_invalid_device_contract(settings, backend, kind, device_id):
    from apps.training.services.resources import validate_resources

    settings.TRAINING_BACKEND = backend
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = (1,)
    with pytest.raises(ValidationError):
        validate_resources({"accelerator_type": kind, "accelerator_count": 0 if kind == "none" else 1,
                            "accelerator_model": "t4" if backend == "argo" else "", "local_gpu_id": device_id})


@pytest.mark.django_db
def test_create_persists_only_a_verified_local_gpu(settings, monkeypatch):
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient
    from apps.catalog.models import ModelProject
    from apps.catalog.tests.test_preview_lifecycle import MemoryStorage

    settings.TRAINING_BACKEND = "docker"
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = (1,)
    monkeypatch.setattr("apps.training.services.jobs.S3Storage", MemoryStorage)
    check = Mock(return_value={"id": GPU})
    monkeypatch.setattr(local_gpu, "require_device", check)
    user = get_user_model().objects.create_user("gpu-create-test@example.com")
    project = ModelProject.objects.create(owner=user, name="gpu project")
    client = APIClient()
    client.force_authenticate(user)
    payload = {"project": str(project.public_id), "name": "gpu", "model_flavor": "pytorch",
               "accelerator_type": "gpu", "accelerator_count": 1, "local_gpu_id": GPU}
    response = client.post("/api/training-jobs/", payload, format="json")
    assert response.status_code == 201
    assert response.data["local_gpu_id"] == GPU
    assert client.get(f'/api/training-jobs/{response.data["id"]}/').data["local_gpu_id"] == GPU
    check.assert_called_once_with(GPU)


@pytest.mark.django_db
def test_docker_dispatch_uses_exact_verified_uuid(settings, monkeypatch):
    from django.contrib.auth import get_user_model
    from apps.catalog.models import ModelProject
    from apps.training.models import TrainingJob
    from apps.training.services.storage_scope import expected_training_uris
    from infrastructure.execution.docker_backends import DockerTrainingBackend

    user = get_user_model().objects.create_user("gpu-dispatch-test@example.com")
    project = ModelProject.objects.create(owner=user, name="gpu project")
    job = TrainingJob(project=project, name="gpu", model_flavor="pytorch", accelerator_type="gpu",
                      accelerator_count=1, local_gpu_id=GPU)
    uris = expected_training_uris(job, "test-bucket")
    job.code_snapshot_uri, job.data_snapshot_uri, job.output_uri = uris["code"], uris["data"], uris["output"]
    docker_client = Mock()
    storage = Mock(bucket="test-bucket")
    storage.presigned_get.return_value = "https://example.invalid/object"
    check = Mock(return_value={"id": GPU})
    monkeypatch.setattr(local_gpu, "require_device", check)
    monkeypatch.setattr("infrastructure.execution.docker_backends.issue_capability", lambda *args, **kw: "capability")
    start = Mock(return_value=Mock(id="container-id"))
    monkeypatch.setattr("infrastructure.execution.job_containers.start", start)
    DockerTrainingBackend(docker_client=docker_client, storage=storage).run(job)
    check.assert_called_once_with(GPU, client=docker_client.client)
    request = start.call_args.kwargs["device_requests"][0]
    assert request["DeviceIDs"] == [GPU]
    assert request["Count"] == 0
