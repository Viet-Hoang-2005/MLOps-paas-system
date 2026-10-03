from unittest.mock import Mock
import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment
from apps.registry.models import ModelVersion
from apps.observability.services.runtime_metrics import runtime_metrics
from infrastructure.docker_metrics import DockerMetricsClient, parse_stats
from infrastructure.local_request_metrics import LocalRequestCounterClient


def test_cpu_cores_and_ram_cgroup_v2():
    stats = {
        "cpu_stats": {"cpu_usage": {"total_usage": 300}, "system_cpu_usage": 3000, "online_cpus": 4},
        "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000},
        "memory_stats": {"usage": 10485760, "stats": {"inactive_file": 2097152}},
    }
    assert parse_stats(stats) == {"cpu": 0.4, "memory": 8}
    stats["memory_stats"]["stats"] = {"total_inactive_file": 1048576}
    assert parse_stats(stats)["memory"] == 9
    stats["cpu_stats"].pop("online_cpus")
    stats["cpu_stats"]["cpu_usage"]["percpu_usage"] = [1, 1]
    assert parse_stats(stats)["cpu"] == 0.2


def test_missing_first_sample_is_not_fake_zero():
    assert parse_stats({}) == {"cpu": None, "memory": None}
    assert parse_stats({"memory_stats": {"usage": 0}})["memory"] == 0
    stats = {"cpu_stats": {"cpu_usage": {"total_usage": 3}, "system_cpu_usage": 100, "online_cpus": 2}}
    assert parse_stats(stats)["cpu"] is None


def test_counter_read_is_bounded_scoped_and_closed(monkeypatch, settings):
    settings.REDIS_URL = "redis://cache.test:6379/1"
    factory = Mock()
    context = Mock(__enter__=Mock(return_value=Mock(hgetall=Mock(return_value={}))), __exit__=Mock(return_value=False))
    factory.return_value = context
    monkeypatch.setattr("infrastructure.local_request_metrics.Redis.from_url", factory)
    assert LocalRequestCounterClient().read(tenant_id="t", project_id="p", version_id="v") == {}
    factory.assert_called_once_with(settings.REDIS_URL, socket_timeout=0.2, socket_connect_timeout=0.2)
    context.__enter__.return_value.hgetall.assert_called_once_with("runtime_requests:t:p:v")
    context.__exit__.assert_called_once()


@pytest.fixture
def deployment(db):
    owner = get_user_model().objects.create_user("metrics-owner@example.test", "password")
    project = ModelProject.objects.create(owner=owner, name="Metrics project")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version)
    current = Deployment.objects.create(version=version, build=build, backend="docker", status="healthy")
    project.active_deployment = current
    project.save()
    return current


def container_for(deployment):
    project = deployment.version.project
    return Mock(
        status="running",
        labels={
            "mlops_project_id": str(project.public_id),
            "mlops_version_id": str(deployment.version.public_id),
            "mlops_deployment_id": str(deployment.public_id),
            "mlops_tenant_id": str(project.owner.tenant_id),
        },
        stats=Mock(return_value={"memory_stats": {"usage": 1048576}}),
    )


def test_only_running_owned_container_is_read(deployment):
    container = container_for(deployment)
    client = Mock()
    client.containers.get.return_value = container
    assert DockerMetricsClient(client).sample(deployment) == {"cpu": None, "memory": 1}
    client.containers.get.assert_called_once_with(f"deploy-{deployment.public_id}")
    container.stats.assert_called_once_with(stream=False)
    container.stats.reset_mock()
    container.labels["mlops_tenant_id"] = str(uuid.uuid4())
    assert DockerMetricsClient(client).sample(deployment) is None
    container.stats.assert_not_called()
    container.status = "exited"
    assert DockerMetricsClient(client).sample(deployment) is None


def test_sdk_client_is_closed_on_error(deployment, monkeypatch):
    client = Mock()
    client.containers.get.side_effect = RuntimeError("internal Docker error")
    factory = Mock(return_value=client)
    monkeypatch.setattr("infrastructure.docker_metrics.docker.from_env", factory)
    with pytest.raises(RuntimeError):
        DockerMetricsClient().sample(deployment)
    factory.assert_called_once_with(timeout=2)
    client.close.assert_called_once()


def test_local_snapshot_and_scoped_request_counter(deployment):
    redis = Mock(read=Mock(return_value={b"count": b"17", b"generation": b"epoch"}))
    docker = Mock(sample=Mock(return_value={"cpu": 0.2, "memory": 100}))
    project = deployment.version.project
    result = runtime_metrics(project, docker=docker, redis=redis)
    assert result["mode"] == "realtime"
    assert result["status"] == "available"
    assert result["snapshot"]["request_counter"] == {"count": 17, "generation": "epoch"}
    assert "series" not in result and "window" not in result
    redis.read.assert_called_once_with(
        tenant_id=project.owner.tenant_id, project_id=project.public_id, version_id=deployment.version.public_id
    )


def test_docker_failure_sanitized_and_redis_failure_does_not_hide_cpu(deployment):
    project = deployment.version.project
    redis = Mock(read=Mock(side_effect=RuntimeError("secret connection string")))
    result = runtime_metrics(project, docker=Mock(sample=Mock(return_value={"cpu": 0, "memory": 1})), redis=redis)
    assert result["snapshot"]["request_counter"] is None
    assert result["snapshot"]["cpu"] == 0
    result = runtime_metrics(project, docker=Mock(sample=Mock(side_effect=RuntimeError("secret socket path"))))
    assert result["status"] == "unavailable" and result["snapshot"] is None
    assert "secret" not in str(result)


def test_no_running_or_deleting_project_never_reads_docker(deployment):
    project = deployment.version.project
    client = Mock()
    project.deletion_state = "deleting"
    assert runtime_metrics(project, docker=client)["snapshot"] is None
    project.active_deployment = None
    assert runtime_metrics(project, docker=client)["snapshot"] is None
    client.sample.assert_not_called()


def test_metrics_endpoint_authorizes_before_container_access(deployment, monkeypatch):
    project = deployment.version.project
    sample = Mock(return_value={"cpu": 1, "memory": 2})
    monkeypatch.setattr("infrastructure.docker_metrics.DockerMetricsClient.sample", sample)
    monkeypatch.setattr(
        "infrastructure.local_request_metrics.LocalRequestCounterClient.read", lambda *args, **kwargs: {}
    )
    url = f"/api/observability/models/{project.public_id}/runtime-metrics/"
    client = APIClient()
    assert client.get(url).status_code == 401
    stranger = get_user_model().objects.create_user("metrics-stranger@example.test", "password")
    client.force_authenticate(stranger)
    assert client.get(url).status_code == 404
    sample.assert_not_called()
    client.force_authenticate(project.owner)
    result = client.get(url + "?container=unrelated&window=24h")
    assert result.status_code == 200
    assert result.data["deployment_id"] == str(deployment.public_id)
    sample.assert_called_once_with(deployment)
