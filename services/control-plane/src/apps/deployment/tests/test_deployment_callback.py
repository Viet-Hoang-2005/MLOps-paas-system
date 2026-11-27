import secrets
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.services.callbacks import issue_callback_token
from apps.deployment.tasks import execute_deployment, mark_deployment_unconfirmed
from apps.observability.services.executions import claim, signed_observation_token
from apps.registry.models import ModelVersion


@pytest.fixture
def deployment(db, settings, monkeypatch):
    settings.CONTROL_PLANE_WEBHOOK_SECRET = secrets.token_urlsafe(48)
    owner = get_user_model().objects.create_user("reporter@example.com", "test-password")
    project = ModelProject.objects.create(owner=owner, name="reporter")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="sklearn", status="ready")
    deployment = Deployment.objects.create(version=version, build=build, backend="argo", status="deploying")
    Endpoint.objects.create(deployment=deployment, public_url="https://example.test/model")
    for name in ("invalidate_model_server_cache", "append_deployment_log"):
        monkeypatch.setattr(f"apps.deployment.tasks.{name}", Mock())
    return deployment


def report(deployment, phase="Succeeded", token=None, workflow_name=None):
    return APIClient().post(
        f"/internal/webhooks/deployments/{deployment.public_id}/",
        {"status": phase, "workflow_name": workflow_name or f"deploy-{deployment.public_id}"},
        format="json",
        HTTP_X_DEPLOYMENT_CALLBACK_TOKEN=token or issue_callback_token(deployment.public_id),
    )


def test_reporter_confirms_readiness_and_replay_is_idempotent(deployment):
    assert report(deployment).data["status"] == "succeeded"
    deployment.refresh_from_db()
    assert deployment.deployed_at is not None
    assert deployment.endpoint.health_status == "healthy"
    assert deployment.external_deployment_id == f"deploy-{deployment.public_id}"
    assert report(deployment, "Failed").data["duplicate"] is True
    deployment.refresh_from_db()
    assert deployment.status == "succeeded"


def test_reporter_rejects_legacy_or_mismatched_workflow_name(deployment):
    import importlib.util
    from pathlib import Path
    import uuid

    job_ops_path = Path(__file__).resolve().parents[6] / "k8s/argo/workflows/operations/scripts/job_ops.py"
    spec = importlib.util.spec_from_file_location("job_ops", job_ops_path)
    job_ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job_ops)

    workflow_name, _ = job_ops.identity(
        {
            "deployment_id": str(deployment.public_id),
            "project_id": str(deployment.version.project.public_id),
            "tenant_id": deployment.version.project.owner.tenant_id,
        },
        "deployment",
    )
    assert workflow_name == f"deploy-{deployment.public_id}"
    assert report(deployment, workflow_name="deploy-model-job-test").status_code == 400
    assert report(deployment, workflow_name=f"deploy-{uuid.uuid4()}").status_code == 400
    assert report(deployment, workflow_name=workflow_name).status_code == 200


def test_reporter_rejects_missing_wrong_resource_expired_token(deployment, monkeypatch):
    url = f"/internal/webhooks/deployments/{deployment.public_id}/"
    assert APIClient().post(url, {}, format="json").status_code == 403
    assert report(deployment, token=issue_callback_token(deployment.build.public_id)).status_code == 403
    token = issue_callback_token(deployment.public_id)
    from apps.deployment.services import callbacks

    original = callbacks.time.time()
    monkeypatch.setattr(callbacks.time, "time", lambda: original + 3601)
    assert report(deployment, token=token).status_code == 403


def test_failure_and_stopped_result_cannot_be_revived(deployment):
    assert report(deployment, "Error").data["status"] == "failed"
    assert report(deployment).data["duplicate"] is True
    Deployment.objects.filter(pk=deployment.pk).update(status="stopped")
    assert report(deployment).data["status"] == "stopped"


def test_timeout_is_unconfirmed_and_late_valid_callback_is_accepted(deployment):
    assert mark_deployment_unconfirmed(str(deployment.public_id)) == "unconfirmed"
    assert report(deployment).data["status"] == "succeeded"
    assert mark_deployment_unconfirmed(str(deployment.public_id)) == "succeeded"


def test_argo_dispatch_schedules_only_one_result_deadline(deployment, monkeypatch):
    backend = Mock(deploy=Mock(return_value=deployment.endpoint))
    monkeypatch.setattr("apps.deployment.tasks.deployment_backend", lambda _: backend)
    deadline = Mock()
    monkeypatch.setattr("apps.deployment.tasks.mark_deployment_unconfirmed.apply_async", deadline)
    assert execute_deployment.run(str(deployment.public_id)) == "deploying"
    deadline.assert_called_once_with(args=[str(deployment.public_id)], countdown=33 * 60)
    deployment.refresh_from_db()
    assert deployment.next_execution_check_at is not None


@pytest.mark.parametrize("healthy", [False, True])
def test_observation_recovers_unconfirmed_deployment_after_health_check(deployment, monkeypatch, healthy):
    assert mark_deployment_unconfirmed(str(deployment.public_id)) == "unconfirmed"
    Deployment.objects.filter(pk=deployment.pk).update(execution_deadline_at=timezone.now())
    backend = Mock()
    backend.health.return_value = healthy, {}
    monkeypatch.setattr("apps.deployment.services.argo_recovery.deployment_backend", lambda _: backend)
    _, lease = claim("deployment", deployment.public_id)[0]
    token = signed_observation_token("deployment", deployment, lease)
    path = f"/internal/executions/deployment/{deployment.public_id}/observations/"
    client = APIClient()
    assert client.post(path, {"status": "completed"}, format="json").status_code == 403
    assert client.post(
        path, {"status": "completed"}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}"
    ).status_code == 200
    deployment.refresh_from_db()
    backend.health.assert_called_once()
    assert deployment.status == ("succeeded" if healthy else "unconfirmed")
    assert deployment.execution_check_token is None
    assert client.post(
        path, {"status": "completed"}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}"
    ).status_code == 403
