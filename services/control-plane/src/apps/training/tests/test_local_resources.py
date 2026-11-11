from django.utils import timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.training.models import LocalTrainingReservation, TrainingJob
from apps.training.services import local_resources as local
from common.api.exceptions import Conflict, ServiceUnavailable


@pytest.mark.parametrize("cpu,memory,expected", [
    (4, 4096, [(1, 512), (1, 1280), (3, 2560)]),
    (4, 6144, [(1, 1024), (1, 2304), (3, 4608)]),
    (8, 8192, [(1, 1536), (3, 3072), (6, 6144)]),
    (1, 2560, [(1, 512), (1, 1024)]),
    (2, 2048, []),
])
def test_profiles_reserve_memory_and_remove_duplicates(cpu, memory, expected):
    assert [(p["vcpu"], p["memory_mb"]) for p in local.profiles(cpu, memory)] == expected
    if memory == 2560:
        assert [p["id"] for p in local.profiles(cpu, memory)] == ["small", "large"]


def test_docker_discovery_checks_limits_and_closes(monkeypatch):
    client = MagicMock()
    client.info.return_value = {"ID": "daemon", "NCPU": 4, "MemTotal": 4096 * local.MIB,
                                "MemoryLimit": True, "CpuCfsQuota": True}
    monkeypatch.setattr(local, "DockerClient", lambda **kwargs: SimpleNamespace(client=client))
    result = local._discover()
    assert result["cpu_profiles"][-1] == {"id": "large", "vcpu": 3, "memory_mb": 2560}
    client.close.assert_called_once()
    client.info.return_value["MemoryLimit"] = False
    assert local._discover()["status"] == "error"


def test_memory_probe_cleans_up_on_success_and_error():
    client = MagicMock()
    client.containers.list.return_value = []
    container = client.containers.create.return_value
    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = b"MemTotal: 4194304 kB\nMemAvailable: 2097152 kB\n"
    assert local._memory_available(client, 4096) == 2048
    container.remove.assert_called_once_with(force=True)
    kwargs = client.containers.create.call_args.kwargs
    assert kwargs["network_disabled"] and "volumes" not in kwargs
    assert kwargs["entrypoint"] == "cat"
    client.images.pull.assert_not_called()
    container.logs.return_value = b"MemAvailable: 123 kB\n"
    with pytest.raises(ValueError):
        local._memory_available(client, 4096)
    assert container.remove.call_count == 2


@pytest.mark.django_db
def test_unreserved_legacy_container_blocks_admission(monkeypatch):
    client = MagicMock()
    container = MagicMock(name="legacy")
    container.name = "training-legacy"
    container.attrs = {"State": {"Status": "running"}, "Config": {"Labels": {}}}
    client.containers.list.return_value = [container]
    monkeypatch.setattr(local, "DockerClient", lambda **kwargs: SimpleNamespace(client=client))
    with pytest.raises(ServiceUnavailable):
        local._check_unmanaged("daemon")
    client.close.assert_called_once()


@pytest.mark.django_db
def test_outstanding_memory_subtracts_verified_running_usage(settings, monkeypatch):
    settings.TRAINING_EXECUTION_WATCH_ENABLED = True
    user = get_user_model().objects.create_user("memory@example.com")
    project = ModelProject.objects.create(owner=user, name="memory")
    current = TrainingJob.objects.create(project=project, vcpu=1, memory_mb=1024, max_runtime_seconds=3600, input_contract="legacy", status="pending")
    other = TrainingJob.objects.create(project=project, vcpu=1, memory_mb=2048,
                                       external_job_id="runtime-id", max_runtime_seconds=3600, input_contract="legacy", status="pending")
    snapshot = {"daemon_id": "daemon", "cpu_profiles": [{"id": "large", "vcpu": 4, "memory_mb": 4096}]}
    with transaction.atomic():
        local.reserve(current, snapshot)
        local.reserve(other, snapshot)
    from infrastructure.execution.job_containers import labels_for
    client = MagicMock()
    container = client.containers.get.return_value
    container.id = "runtime-id"
    container.attrs = {"State": {"Status": "running"}, "Config": {"Labels": labels_for(other, "training")}}
    monkeypatch.setattr("infrastructure.docker_metrics.parse_stats", lambda data: {"memory": 768})
    assert local._outstanding_memory(client, "daemon", current) == 1024 + 1280
    container.exec_run.assert_not_called()


@pytest.mark.django_db
def test_reservation_is_shared_and_released_only_explicitly(settings):
    settings.TRAINING_EXECUTION_WATCH_ENABLED = True
    first = get_user_model().objects.create_user("local-first@example.com")
    second = get_user_model().objects.create_user("local-second@example.com")
    jobs = [TrainingJob.objects.create(project=ModelProject.objects.create(owner=user, name=str(i)),
                                       vcpu=2, memory_mb=2048, max_runtime_seconds=3600, input_contract="legacy", status="pending") for i, user in enumerate((first, second))]
    snapshot = {"daemon_id": "daemon", "cpu_profiles": [{"id": "large", "vcpu": 3, "memory_mb": 4096}]}
    with transaction.atomic():
        local.reserve(jobs[0], snapshot)
    with pytest.raises(Conflict), transaction.atomic():
        local.reserve(jobs[1], snapshot)
    assert local.totals("daemon") == (2, 2048)
    local.release(jobs[0])
    assert local.totals("daemon") == (0, 0)
    with transaction.atomic():
        local.reserve(jobs[1], snapshot)
    assert LocalTrainingReservation.objects.get(job_id=jobs[1].public_id).active


@pytest.mark.django_db
def test_dispatch_guard_rejects_low_memory_and_releases_lock(settings, monkeypatch):
    settings.TRAINING_EXECUTION_WATCH_ENABLED = True
    user = get_user_model().objects.create_user("guard@example.com")
    job = TrainingJob.objects.create(project=ModelProject.objects.create(owner=user, name="guard"),
                                      vcpu=2, memory_mb=2048, max_runtime_seconds=3600, input_contract="legacy", status="pending")
    snapshot = {"daemon_id": "daemon", "status": "available", "total_memory_mb": 8192,
                "cpu_profiles": [{"id": "large", "vcpu": 6, "memory_mb": 6144}]}
    with transaction.atomic():
        local.reserve(job, snapshot)
    lock = MagicMock()
    lock.acquire.return_value = True
    lock.owned.return_value = True
    monkeypatch.setattr(local.cache, "lock", lambda *args, **kwargs: lock, raising=False)
    monkeypatch.setattr(local, "require_capacity", lambda **kwargs: snapshot)
    monkeypatch.setattr(local, "_memory_available", lambda *_: 1000)
    with pytest.raises(ServiceUnavailable), local.dispatch_guard(job, MagicMock()):
        pytest.fail("must not dispatch")
    lock.release.assert_called_once()


@pytest.mark.django_db
def test_capability_exposes_dynamic_profiles_and_only_aggregate_usage(settings, monkeypatch):
    settings.TRAINING_BACKEND = "docker"
    settings.TRAINING_GPU_ENABLED = False
    snapshot = {"status": "available", "reason": "", "daemon_id": "private-id", "total_vcpu": 4,
                "total_memory_mb": 4096, "cpu_profiles": local.profiles(4, 4096)}
    monkeypatch.setattr(local, "capacity", lambda **kwargs: snapshot)
    user = get_user_model().objects.create_user("capacity@example.com")
    client = APIClient()
    client.force_authenticate(user)
    data = client.get("/api/training-jobs/runtime-capabilities/?refresh=1").data
    assert data["cpu_profiles"][-1] == {"id": "large", "vcpu": 3, "memory_mb": 2560}
    assert data["local_resources"]["available_memory_mb"] == 2560
    assert "daemon_id" not in data["local_resources"]


@pytest.mark.django_db
def test_reconciliation_releases_reservation_only_after_confirmed_stop(settings):
    from apps.observability.services import executions
    settings.TRAINING_EXECUTION_WATCH_ENABLED = True
    user = get_user_model().objects.create_user("release@example.com")
    job = TrainingJob.objects.create(project=ModelProject.objects.create(owner=user, name="release"),
                                      backend="docker", status="queued", vcpu=1, memory_mb=1024, max_runtime_seconds=3600, input_contract="legacy", submitted_at=timezone.now())
    snapshot = {"daemon_id": "daemon", "cpu_profiles": [{"id": "large", "vcpu": 2, "memory_mb": 2048}]}
    with transaction.atomic():
        local.reserve(job, snapshot)
    token = executions.claim("training", str(job.public_id))[0][1]
    executions.apply_observation("training", str(job.public_id), token, {"status": "error", "error": "Docker unavailable"})
    assert local.totals("daemon") == (1, 1024)
    token = executions.claim("training", str(job.public_id))[0][1]
    executions.apply_observation("training", str(job.public_id), token, {"status": "stopped"})
    assert local.totals("daemon") == (0, 0)


@pytest.mark.django_db(transaction=True)
def test_concurrent_reservations_share_a_postgres_pool(settings):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connection

    if connection.vendor != "postgresql":
        pytest.skip("row-lock concurrency requires PostgreSQL")
    settings.TRAINING_EXECUTION_WATCH_ENABLED = True
    user = get_user_model().objects.create_user("concurrent@example.com")
    project = ModelProject.objects.create(owner=user, name="concurrent")
    jobs = [TrainingJob.objects.create(project=project, vcpu=2, memory_mb=2048, max_runtime_seconds=3600, input_contract="legacy", status="pending") for i in range(2)]
    snapshot = {"daemon_id": "concurrent-daemon", "cpu_profiles": [{"id": "large", "vcpu": 2, "memory_mb": 2048}]}
    barrier = Barrier(2)

    def attempt(job):
        close_old_connections()
        barrier.wait(timeout=10)
        try:
            with transaction.atomic():
                local.reserve(job, snapshot)
            return "accepted"
        except Conflict:
            return "rejected"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, jobs)) == ["accepted", "rejected"]
