from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.ct.models import DatasetSnapshot
from apps.drift.models import DriftMonitor, DriftRun
from apps.registry.models import ModelVersion
from infrastructure.execution.argo_backends import ArgoDriftBackend
from infrastructure.execution.docker_backends import DockerDriftBackend


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("drift-snapshot-owner@example.com", "password123")


@pytest.fixture
def project(owner):
    return ModelProject.objects.create(owner=owner, name="Drift Snapshot Project")


@pytest.fixture
def reference_snapshot(project):
    return DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://bucket/reference/reference_data.parquet",
        manifest_checksum="sha256:refparquet123",
        schema_checksum="sha256:schema123",
    )


@pytest.fixture
def version(project, reference_snapshot):
    return ModelVersion.objects.create(
        project=project,
        version="1",
        reference_snapshot=reference_snapshot,
    )


@pytest.mark.django_db
def test_drift_monitor_auto_links_version_reference_snapshot(owner, version, reference_snapshot):
    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(
        "/api/drift-monitors/",
        {
            "version": str(version.public_id),
            "name": "auto-snapshot-monitor",
            "trigger_threshold": 1500,
        },
        format="json",
    )

    assert response.status_code == 201
    payload = response.data
    assert payload["name"] == "auto-snapshot-monitor"
    assert payload["reference_snapshot_id"] == str(reference_snapshot.public_id)
    assert "reference_asset_id" not in payload
    assert "reference_asset_name" not in payload

    monitor = DriftMonitor.objects.get(public_id=payload["id"])
    assert monitor.reference_snapshot == reference_snapshot


@pytest.mark.django_db
def test_docker_and_argo_drift_backend_use_reference_snapshot(version, reference_snapshot):
    monitor = DriftMonitor.objects.create(
        version=version,
        reference_snapshot=reference_snapshot,
        name="test-snapshot-exec-monitor",
        backend="docker",
    )
    run = DriftRun.objects.create(
        monitor=monitor,
        idempotency_key="drift-snap-run-1",
        status="pending",
    )

    presigned_calls = []

    def fake_presigned_get(uri, ttl):
        presigned_calls.append(uri)
        return f"https://s3.test/presigned?uri={uri}&ttl={ttl}"

    fake_storage = SimpleNamespace(
        bucket="test-bucket",
        presigned_get=fake_presigned_get,
        presigned_put=lambda uri, ttl, ct: f"https://s3.test/upload?uri={uri}",
    )

    # 1. Test DockerDriftBackend
    fake_container = SimpleNamespace(id="docker-container-snap-1")
    fake_docker = SimpleNamespace(run=Mock(return_value=fake_container))

    docker_backend = DockerDriftBackend(docker_client=fake_docker, storage=fake_storage)
    docker_backend.run(run)

    fake_docker.run.assert_called_once()
    docker_call_kwargs = fake_docker.run.call_args[1]
    env = docker_call_kwargs["environment"]
    assert env["REFERENCE_DATA_URL"] == f"https://s3.test/presigned?uri={reference_snapshot.manifest_uri}&ttl=7200"
    assert reference_snapshot.manifest_uri in presigned_calls

    # 2. Test ArgoDriftBackend
    argo_backend = ArgoDriftBackend(storage=fake_storage)
    argo_backend.trigger = Mock(return_value={"triggered": True, "workflow": "test-wf"})

    argo_backend.run(run)

    argo_backend.trigger.assert_called_once()
    argo_payload = argo_backend.trigger.call_args[0][0]
    assert argo_payload["reference_data_url"] == f"https://s3.test/presigned?uri={reference_snapshot.manifest_uri}&ttl=7200"


@pytest.mark.django_db
def test_monitor_uses_immutable_version_reference_snapshot(version, reference_snapshot):
    monitor = DriftMonitor.objects.create(
        version=version,
        reference_snapshot=reference_snapshot,
        name="fallback-monitor",
        backend="docker",
    )
    run = DriftRun.objects.create(
        monitor=monitor,
        idempotency_key="drift-fallback-run-1",
        status="pending",
    )

    fake_storage = SimpleNamespace(
        bucket="test-bucket",
        presigned_get=lambda uri, ttl: f"https://s3.test/presigned?uri={uri}",
        presigned_put=lambda uri, ttl, ct: f"https://s3.test/upload?uri={uri}",
    )
    fake_container = SimpleNamespace(id="docker-container-fallback-1")
    fake_docker = SimpleNamespace(run=Mock(return_value=fake_container))

    docker_backend = DockerDriftBackend(docker_client=fake_docker, storage=fake_storage)
    docker_backend.run(run)

    docker_call_kwargs = fake_docker.run.call_args[1]
    env = docker_call_kwargs["environment"]
    assert env["REFERENCE_DATA_URL"] == f"https://s3.test/presigned?uri={reference_snapshot.manifest_uri}"
