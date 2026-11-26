from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.catalog.services.deletion import run_project_cleanup
from apps.deployment.models import Build, Deployment
from apps.drift.models import DriftMonitor, DriftRun
from apps.registry.models import ModelVersion
from infrastructure.execution.argo_backends import ArgoDeploymentBackend, ArgoDriftBackend


@pytest.mark.django_db
def test_project_waits_for_both_argo_runtime_confirmations(monkeypatch, settings):
    cache.clear()
    settings.ARGO_RECONCILE_WEBHOOK_URL = "http://events/reconcile"
    owner = get_user_model().objects.create_user("argo-stop@example.test", "password")
    project = ModelProject.objects.create(owner=owner, name="Argo stop", deletion_state="deleting")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, status="ready")
    deployment = Deployment.objects.create(
        version=version, build=build, status="stopped", backend="argo", stopped_at=timezone.now()
    )
    monitor = DriftMonitor.objects.create(version=version, backend="argo")
    run = DriftRun.objects.create(monitor=monitor, status="cancelled", idempotency_key="argo-stop")

    argo = Mock()
    serving = ArgoDeploymentBackend(client=argo, storage=Mock())
    drift = ArgoDriftBackend(client=argo, storage=Mock())
    monkeypatch.setattr("infrastructure.execution.deployment_backend", lambda _: serving)
    monkeypatch.setattr("infrastructure.execution.drift_backend", lambda _: drift)
    project_cleanup = Mock()
    project_cleanup.run.return_value = {"dispatched": True}
    monkeypatch.setattr("apps.catalog.services.deletion.project_cleanup_backend", lambda: project_cleanup)
    resume = Mock()
    monkeypatch.setattr("apps.catalog.tasks.execute_project_deletion.delay", resume)

    assert run_project_cleanup(project)["waiting_for_stop"]
    assert run_project_cleanup(project)["waiting_for_stop"]
    assert argo.trigger.call_count == 2
    serving_request, drift_request = [call.args[1] for call in argo.trigger.call_args_list]
    project_cleanup.run.assert_not_called()

    client = APIClient()
    serving_path = f"/internal/executions/deployment/{deployment.public_id}/stops/"
    drift_path = f"/internal/executions/drift/{run.public_id}/stops/"

    def report(path, payload, status):
        return client.post(
            path, {"status": status}, format="json", HTTP_AUTHORIZATION=f"Bearer {payload['callback_token']}"
        ).status_code

    assert report(drift_path, serving_request, "stopped") == 403
    assert report(serving_path, serving_request, "error") == 200
    assert run_project_cleanup(project)["waiting_for_stop"]
    assert report(serving_path, serving_request, "stopped") == 200
    resume.assert_not_called()
    assert report(drift_path, drift_request, "stopped") == 200
    resume.assert_called_once_with(str(project.public_id))
    assert run_project_cleanup(project) == {"dispatched": True}
    project_cleanup.run.assert_called_once()


@pytest.mark.django_db
def test_cancelled_argo_drift_run_can_only_be_deleted_after_confirmation(monkeypatch, settings):
    settings.ARGO_RECONCILE_WEBHOOK_URL = "http://events/reconcile"
    owner = get_user_model().objects.create_user("argo-drift-delete@example.test", "password")
    project = ModelProject.objects.create(owner=owner, name="Drift stop")
    version = ModelVersion.objects.create(project=project, version="1")
    monitor = DriftMonitor.objects.create(version=version, backend="argo")
    run = DriftRun.objects.create(monitor=monitor, status="cancelled", idempotency_key="already-cancelled")
    argo = Mock()
    storage = Mock(bucket="artifacts")
    backend = ArgoDriftBackend(client=argo, storage=storage)
    monkeypatch.setattr("apps.drift.services.deletion.drift_backend", lambda _: backend)
    monkeypatch.setattr("apps.drift.services.deletion.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.drift.services.deletion.redis_client", Mock())

    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/drift-monitors/runs/{run.public_id}/"
    assert client.delete(url).status_code == 503
    assert DriftRun.objects.filter(pk=run.pk).exists()
    storage.delete_prefix.assert_not_called()
    payload = argo.trigger.call_args.args[1]
    callback = APIClient().post(
        f"/internal/executions/drift/{run.public_id}/stops/",
        {"status": "stopped"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {payload['callback_token']}",
    )
    assert callback.status_code == 200
    assert client.delete(url).status_code == 204
    assert not DriftRun.objects.filter(pk=run.pk).exists()
    storage.delete_prefix.assert_called_once()
