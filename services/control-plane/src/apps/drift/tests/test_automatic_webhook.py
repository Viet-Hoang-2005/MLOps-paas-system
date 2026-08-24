from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from infrastructure.execution.argo_backends import ArgoDriftBackend
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject, WorkspaceAsset
from apps.drift.models import DriftMonitor, DriftRun
from apps.registry.models import ModelVersion


def _monitor_fixture():
    owner = get_user_model().objects.create_user("automatic-drift@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="automatic drift")
    version = ModelVersion.objects.create(project=project, version="1")
    asset = WorkspaceAsset.objects.create(
        project=project,
        kind="data",
        relative_path="reference.csv",
        s3_uri="s3://bucket/reference.csv",
    )
    return version, asset


@pytest.mark.django_db
@override_settings(CONTROL_PLANE_WEBHOOK_SECRET="test-webhook-secret")
def test_automatic_drift_webhook_creates_one_durable_threshold_crossing(monkeypatch):
    version, asset = _monitor_fixture()
    monitor = DriftMonitor.objects.create(
        version=version,
        reference_asset=asset,
        name="default",
        trigger_threshold=100,
    )
    created_runs = Mock()
    monkeypatch.setattr("apps.drift.services.automatic.production_data_count_for_version", lambda _version: 100)
    monkeypatch.setattr("apps.drift.services.automatic.request_run", created_runs)
    client = APIClient()
    headers = {"HTTP_X_CONTROL_PLANE_SECRET": "test-webhook-secret"}
    payload = {"model_version_id": str(version.public_id)}

    first = client.post("/internal/webhooks/automatic-drift/", payload, format="json", **headers)
    duplicate = client.post("/internal/webhooks/automatic-drift/", payload, format="json", **headers)

    monitor.refresh_from_db()
    assert first.status_code == 202
    assert first.data == {"status": "accepted", "triggered_runs": 1}
    assert duplicate.data == {"status": "accepted", "triggered_runs": 0}
    assert monitor.last_automatic_trigger_count == 100
    created_runs.assert_called_once_with(
        monitor,
        f"automatic-drift:{monitor.public_id}:1",
    )


@pytest.mark.django_db
@override_settings(CONTROL_PLANE_WEBHOOK_SECRET="test-webhook-secret")
def test_automatic_drift_webhook_does_not_trigger_before_threshold(monkeypatch):
    version, asset = _monitor_fixture()
    monitor = DriftMonitor.objects.create(
        version=version,
        reference_asset=asset,
        name="default",
        trigger_threshold=100,
        last_automatic_trigger_count=50,
    )
    request_run = Mock()
    monkeypatch.setattr("apps.drift.services.automatic.production_data_count_for_version", lambda _version: 149)
    monkeypatch.setattr("apps.drift.services.automatic.request_run", request_run)

    response = APIClient().post(
        "/internal/webhooks/automatic-drift/",
        {"model_version_id": str(version.public_id)},
        format="json",
        HTTP_AUTHORIZATION="Bearer test-webhook-secret",
    )

    monitor.refresh_from_db()
    assert response.data == {"status": "accepted", "triggered_runs": 0}
    assert monitor.last_automatic_trigger_count == 50
    request_run.assert_not_called()


@pytest.mark.django_db
def test_automatic_drift_webhook_requires_secret_and_uuid():
    client = APIClient()
    assert client.post("/internal/webhooks/automatic-drift/", {}, format="json").status_code == 403
    response = client.post(
        "/internal/webhooks/automatic-drift/",
        {"model_version_id": "not-a-uuid"},
        format="json",
        HTTP_X_CONTROL_PLANE_SECRET="local-webhook-secret",
    )
    assert response.status_code == 400


@pytest.mark.django_db
@override_settings(
    ARGO_DRIFT_WEBHOOK_URL="http://argo-events/drift",
    CONTROL_PLANE_INTERNAL_URL="http://control-plane:8000",
)
def test_automatic_drift_run_dispatches_complete_argo_payload():
    version, asset = _monitor_fixture()
    monitor = DriftMonitor.objects.create(version=version, reference_asset=asset, name="default")
    run = DriftRun.objects.create(monitor=monitor, idempotency_key="automatic-drift-argo")
    captured = {}

    class Storage:
        bucket = "artifacts"

        def presigned_get(self, uri, _expires_in):
            return f"get:{uri}"

        def presigned_put(self, uri, _expires_in, content_type):
            return f"put:{content_type}:{uri}"

    class Client:
        def trigger(self, url, payload):
            captured["url"] = url
            captured["payload"] = payload
            return {"accepted": True}

    ArgoDriftBackend(client=Client(), storage=Storage()).run(run)

    payload = captured["payload"]
    assert captured["url"] == "http://argo-events/drift"
    assert payload["job_id"] == str(run.public_id)
    assert payload["model_version_id"] == str(version.public_id)
    assert payload["reference_data_url"] == "get:s3://bucket/reference.csv"
    assert payload["control_plane_webhook_url"] == (
        f"http://control-plane:8000/internal/webhooks/drift-runs/{run.public_id}/"
    )
    assert payload["report_json_s3_uri"].endswith("/report.json")
    assert payload["summary_json_upload_url"].endswith("/summary.json")
