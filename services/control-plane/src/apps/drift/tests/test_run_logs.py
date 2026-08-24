import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject, WorkspaceAsset
from apps.drift.models import DriftMonitor, DriftRun
from apps.drift.services import logs as log_service
from apps.registry.models import ModelVersion


class FakeRedis:
    def lrange(self, _key, start, _end):
        return [b"load production data", b"run report"][start:]

    def llen(self, _key):
        return 2


@pytest.mark.django_db
def test_drift_run_logs_are_streamed_only_to_run_owner(monkeypatch):
    owner = get_user_model().objects.create_user("drift-owner@example.com", "password123")
    other = get_user_model().objects.create_user("drift-other@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="drift logs")
    version = ModelVersion.objects.create(project=project, version="1")
    asset = WorkspaceAsset.objects.create(
        project=project,
        kind="data",
        relative_path="reference.csv",
        s3_uri="s3://bucket/reference.csv",
    )
    monitor = DriftMonitor.objects.create(version=version, reference_asset=asset, name="default")
    run = DriftRun.objects.create(monitor=monitor, idempotency_key="drift-log-test", status="running")
    monkeypatch.setattr(log_service.Redis, "from_url", lambda _url: FakeRedis())
    client = APIClient()
    client.force_authenticate(other)

    assert client.get(f"/api/drift-monitors/runs/{run.public_id}/logs/").status_code == 404

    client.force_authenticate(owner)
    response = client.get(f"/api/drift-monitors/runs/{run.public_id}/logs/?offset=1")

    assert response.status_code == 200
    assert response.data["logs"] == ["run report"]
    assert response.data["next_offset"] == 2
    assert response.data["status"] == "running"
