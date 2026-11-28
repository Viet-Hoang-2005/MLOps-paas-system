from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.drift.models import DriftMonitor, DriftRun
from apps.drift.monitors.tasks import cleanup_drift_monitor_task
from apps.drift.runs.lifecycle import request_run
from apps.registry.models import ModelArtifact, ModelVersion
from common.api.exceptions import Conflict, ServiceUnavailable


@pytest.mark.django_db
def test_delete_drift_run_cancels_active_container_and_cleans_s3_and_redis(monkeypatch):
    owner = get_user_model().objects.create_user("drift-del@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Drift Delete")
    version = ModelVersion.objects.create(project=project, version="1")
    monitor = DriftMonitor.objects.create(version=version, name="m1", reference_uri="s3://bucket/ref.csv")
    run = DriftRun.objects.create(
        monitor=monitor,
        status="running",
        idempotency_key="drift-run-del-1",
        report_html_uri="s3://bucket/report.html",
        report_json_uri="s3://bucket/report.json",
        summary_uri="s3://bucket/summary.json",
    )

    cancelled = []
    monkeypatch.setattr(
        "apps.drift.monitors.deletion.drift_backend",
        lambda _backend: Mock(cancel=lambda item: cancelled.append(str(item.public_id))),
    )
    storage = Mock(bucket="bucket")
    monkeypatch.setattr("apps.drift.monitors.deletion.S3Storage", lambda: storage)
    redis_mock = Mock()
    monkeypatch.setattr("apps.drift.monitors.deletion.redis_client", lambda: redis_mock)

    client = APIClient()
    client.force_authenticate(owner)
    response = client.delete(f"/api/drift-runs/{run.public_id}/")

    assert response.status_code == 204
    assert not DriftRun.objects.filter(pk=run.pk).exists()
    assert cancelled == [str(run.public_id)]
    assert storage.delete_prefix.called
    assert storage.delete.call_count == 3
    redis_mock.delete.assert_called_once_with(f"drift_logs:{run.public_id}")


@pytest.mark.django_db
def test_delete_drift_monitor_preserves_shared_model_artifact_reference(
    monkeypatch, django_capture_on_commit_callbacks
):
    owner = get_user_model().objects.create_user("drift-mon-del@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Monitor Delete")
    version = ModelVersion.objects.create(project=project, version="1")
    shared_uri = "s3://bucket/shared/ref.csv"
    ModelArtifact.objects.create(version=version, kind="reference_data", name="ref.csv", uri=shared_uri)
    monitor = DriftMonitor.objects.create(version=version, name="m1", reference_uri=shared_uri)
    DriftRun.objects.create(monitor=monitor, status="completed", idempotency_key="drift-run-del-2")

    storage = Mock(bucket="bucket")
    monkeypatch.setattr("apps.drift.monitors.deletion.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.drift.monitors.deletion.redis_client", lambda: Mock())

    def assert_run_blocked(_prefix):
        assert DriftMonitor.objects.get(pk=monitor.pk).deletion_requested
        with pytest.raises(Conflict, match="monitor or model version is being deleted"):
            request_run(monitor)

    storage.delete_prefix.side_effect = assert_run_blocked

    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/drift-monitors/{monitor.public_id}/"
    dispatch = Mock()
    monkeypatch.setattr(cleanup_drift_monitor_task, "apply_async", dispatch)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete(url)
        dispatch.assert_not_called()
    assert response.status_code == 202
    assert response.data["deletion_requested"] is True
    dispatch.assert_called_once_with(args=[str(monitor.public_id)], retry=False)
    assert client.get(url).data["deletion_requested"] is True
    assert client.patch(url, {"trigger_threshold": 100}).status_code == 409
    storage.delete_prefix.assert_not_called()

    assert cleanup_drift_monitor_task.run(str(monitor.public_id)) == "deleted"
    assert client.get(url).status_code == 404
    assert not DriftMonitor.objects.filter(pk=monitor.pk).exists()
    assert shared_uri not in [call.args[0] for call in storage.delete.call_args_list]


@pytest.mark.django_db
@pytest.mark.parametrize("failure", ["run-prefix", "monitor-prefix", "run-object", "cancel"])
def test_drift_delete_keeps_rows_on_cleanup_failure_and_can_retry(monkeypatch, failure):
    owner = get_user_model().objects.create_user("drift-retry@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Drift Retry")
    version = ModelVersion.objects.create(project=project, version="1")
    monitor = DriftMonitor.objects.create(version=version, name="retry")
    run = DriftRun.objects.create(
        monitor=monitor,
        status="running" if failure == "cancel" else "completed",
        idempotency_key="retry",
        report_html_uri="s3://bucket/report.html",
    )
    storage = Mock(bucket="bucket")
    backend = Mock()
    monkeypatch.setattr("apps.drift.monitors.deletion.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.drift.monitors.deletion.redis_client", Mock())
    monkeypatch.setattr("apps.drift.monitors.deletion.drift_backend", lambda _backend: backend)
    if failure in {"run-prefix", "monitor-prefix"}:
        calls = [TimeoutError("storage timeout")]
        if failure == "monitor-prefix":
            calls.insert(0, None)
        storage.delete_prefix.side_effect = calls
    elif failure == "run-object":
        storage.delete.side_effect = TimeoutError("storage timeout")
    else:
        backend.cancel.side_effect = TimeoutError("runtime timeout")

    client = APIClient()
    client.force_authenticate(owner)
    delete_monitor = failure == "monitor-prefix"
    url = (
        f"/api/drift-monitors/{monitor.public_id}/" if delete_monitor else f"/api/drift-runs/{run.public_id}/"
    )
    if delete_monitor:
        assert client.delete(url).status_code == 202
        with pytest.raises(ServiceUnavailable):
            cleanup_drift_monitor_task.run(str(monitor.public_id))
        assert client.get(url).data["deletion_requested"] is True
    else:
        assert client.delete(url).status_code == 503
    assert DriftMonitor.objects.filter(pk=monitor.pk).exists()
    assert DriftRun.objects.filter(pk=run.pk, report_html_uri=run.report_html_uri).exists()

    storage.delete_prefix.side_effect = None
    storage.delete.side_effect = None
    backend.cancel.side_effect = None
    backend.cancel.return_value = {"confirmed": True}
    if delete_monitor:
        assert cleanup_drift_monitor_task.run(str(monitor.public_id)) == "deleted"
    else:
        assert client.delete(url).status_code == 204
    assert not DriftRun.objects.filter(pk=run.pk).exists()
    assert DriftMonitor.objects.filter(pk=monitor.pk).exists() is not delete_monitor
