"""Argo build webhook trust, build cancellation and failed-deployment runtime cleanup."""

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.builds.cleanup import cleanup_failed_build_artifacts
from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.serving.callback_tokens import issue_callback_token
from apps.deployment.serving.rollout_tasks import stop_deployment
from apps.observability.execution.reconciliation import _reconcile_argo_deadlines, reconcile, scan
from apps.observability.execution.tasks import reconcile_job_execution
from apps.registry.models import ModelVersion
from infrastructure.execution.build import ArgoBuildBackend
from infrastructure.images.references import temporary_image_reference

SECRET = "test-webhook-secret"
DIGEST = "sha256:" + "a" * 64


@pytest.fixture
def project(db, settings):
    settings.CONTROL_PLANE_WEBHOOK_SECRET = SECRET
    settings.HARBOR_REGISTRY_URL = "registry.example"
    settings.HARBOR_USER_PROJECT = "user-images"
    owner = get_user_model().objects.create_user("argo-hardening@example.com", "test-password")
    return ModelProject.objects.create(owner=owner, name="argo-hardening")


@pytest.fixture
def build(project):
    return Build.objects.create(
        project=project,
        flavor="sklearn",
        backend="argo",
        status="building",
        package_uri="s3://bucket/package.zip",
    )


def expected_image(build):
    return temporary_image_reference(
        build.project.public_id, build.public_id, registry="registry.example", registry_project="user-images"
    )


def post_build(build, **payload):
    return APIClient().post(
        f"/internal/webhooks/builds/{build.public_id}/",
        payload,
        format="json",
        HTTP_X_CONTROL_PLANE_SECRET=SECRET,
    )


def success_payload(build, **overrides):
    return {
        "status": "success",
        "image_uri": expected_image(build),
        "image_digest": DIGEST,
        "package_manifest": {"flavor": "sklearn"},
        **overrides,
    }


@pytest.mark.parametrize("correct_digest, deadline_elapsed", [(True, False), (False, False), (True, True)])
def test_build_recovers_from_storage_without_workflow_or_callback(
    build, monkeypatch, settings, correct_digest, deadline_elapsed
):
    settings.ARGO_RECONCILE_WEBHOOK_URL = "http://argo-events/reconcile"
    settings.CONTROL_PLANE_INTERNAL_URL = "http://mlops-paas-control-plane:8000"
    argo = Mock()
    queued = Mock()
    storage = Mock(bucket="bucket")
    storage.read.return_value = json.dumps(success_payload(build, build_id=str(build.public_id)))
    storage.head.return_value.size_bytes = 1024
    harbor = Mock()
    harbor.artifact_digest.return_value = DIGEST if correct_digest else "sha256:" + "b" * 64
    monkeypatch.setattr(reconcile_job_execution, "apply_async", queued)
    monkeypatch.setattr("apps.observability.execution.reconciliation.build_backend", lambda _: ArgoBuildBackend(
        client=argo, storage=storage,
    ))
    monkeypatch.setattr("apps.deployment.execution.argo_recovery.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.deployment.execution.argo_recovery.HarborClient", lambda: harbor)
    if deadline_elapsed:
        past = timezone.now() - timedelta(minutes=1)
        Build.objects.filter(pk=build.pk).update(execution_deadline_at=past, callback_wait_until=past)

    assert scan() == 1
    kind, public_id, token = queued.call_args.kwargs["args"]
    assert (kind, public_id) == ("build", str(build.public_id))
    worker_status = reconcile(kind, public_id, token)
    if deadline_elapsed:
        assert worker_status == "ready"
        argo.trigger.assert_not_called()
    else:
        assert worker_status == "awaiting_observation"
        payload = argo.trigger.call_args.args[1]
        assert payload["stop"] is False
        path = f"/internal/executions/build/{build.public_id}/observations/"
        result = APIClient().post(
            path, {"status": "not_found"}, format="json", HTTP_AUTHORIZATION=f"Bearer {payload['callback_token']}"
        )
        assert result.status_code == 200

    build.refresh_from_db()
    assert build.status == ("ready" if correct_digest else "building")
    assert build.image_digest == (DIGEST if correct_digest else "")
    assert build.execution_check_token is None
    assert storage.read.call_args.args[0].endswith(f"/builds/{build.public_id}/artifacts/build-result.json")
    assert harbor.artifact_digest.call_args.args[0] == expected_image(build)


@pytest.mark.parametrize(
    "overrides",
    [
        {"image_uri": "registry.example/user-images/image-someone-else:build-1"},
        {"image_uri": ""},
        {"image_digest": "latest"},
        {"image_digest": ""},
        {"package_manifest": {}},
        {"package_uri": "s3://bucket/other-tenant/package.zip"},
    ],
)
def test_argo_success_rejects_values_not_scoped_to_the_build(build, monkeypatch, overrides):
    complete = Mock()
    monkeypatch.setattr("apps.deployment.builds.registration.complete_build", complete)
    assert post_build(build, **success_payload(build, **overrides)).status_code == 400
    complete.assert_not_called()
    build.refresh_from_db()
    assert build.status == "building"


def test_argo_success_registers_only_the_build_scoped_image(build, monkeypatch):
    complete = Mock(side_effect=lambda build, **kwargs: build)
    monkeypatch.setattr("apps.deployment.builds.registration.complete_build", complete)
    assert post_build(build, **success_payload(build)).status_code == 200
    kwargs = complete.call_args.kwargs
    assert kwargs["image_uri"] == expected_image(build)
    assert kwargs["image_digest"] == DIGEST


def test_argo_failure_never_stores_a_reporter_chosen_image(build, monkeypatch):
    monkeypatch.setattr("apps.deployment.builds.callbacks.cleanup_failed_build_artifacts.delay", Mock())
    response = post_build(
        build,
        status="failed",
        image_uri="registry.example/user-images/image-victim:v1",
        image_digest="not-a-digest",
        error_message="boom",
    )
    assert response.status_code == 200
    build.refresh_from_db()
    assert build.status == "failed"
    assert build.image_uri == ""
    assert build.image_digest == ""


def test_late_callback_of_a_cancelled_argo_build_cleans_up_its_output(
    build, monkeypatch, django_capture_on_commit_callbacks
):
    Build.objects.filter(pk=build.pk).update(status="cancelled")
    cleanup = Mock()
    monkeypatch.setattr("apps.deployment.builds.callbacks.cleanup_failed_build_artifacts.delay", cleanup)
    with django_capture_on_commit_callbacks(execute=True):
        response = post_build(build, **success_payload(build))
    assert response.data["duplicate"] is True
    build.refresh_from_db()
    assert build.status == "cancelled"
    assert build.image_uri == expected_image(build)
    cleanup.assert_called_once_with(str(build.public_id), True)


def test_argo_cancel_asks_the_cluster_to_terminate_the_build_workflow(build, settings):
    settings.ARGO_RECONCILE_WEBHOOK_URL = "http://argo-events/reconcile"
    client = SimpleNamespace(trigger=Mock(return_value={"ok": True}))
    assert ArgoBuildBackend(client=client, storage=object()).cancel(build) == {"confirmed": False}
    url, payload = client.trigger.call_args.args
    assert url == settings.ARGO_RECONCILE_WEBHOOK_URL
    assert payload["kind"] == "build"
    assert payload["stop"] is True
    assert payload["resource_id"] == str(build.public_id)
    assert payload["project_id"] == str(build.project.public_id)
    assert payload["tenant_id"] == build.project.owner.tenant_id


def test_argo_cancel_confirms_an_undispatched_build_without_contacting_argo(build):
    build.status = "queued"
    client = SimpleNamespace(trigger=Mock())
    assert ArgoBuildBackend(client=client, storage=object()).cancel(build) == {"confirmed": True}
    client.trigger.assert_not_called()


def test_argo_cleanup_retries_when_the_cluster_cannot_be_reached(build, monkeypatch):
    Build.objects.filter(pk=build.pk).update(status="cancelled", started_at=timezone.now())
    backend = Mock(cancel=Mock(side_effect=ConnectionError("argo-events down")))
    monkeypatch.setattr("infrastructure.execution.build_backend", lambda _: backend)
    storage = Mock()
    monkeypatch.setattr("apps.deployment.builds.cleanup.S3Storage", storage)
    assert cleanup_failed_build_artifacts.autoretry_for == (Exception,)
    with pytest.raises(ConnectionError):
        cleanup_failed_build_artifacts.run(str(build.public_id))
    storage.assert_not_called()


def test_argo_deadline_waits_for_stop_before_cleaning_generated_tag(
    build, monkeypatch, settings, django_capture_on_commit_callbacks
):
    cache.clear()
    settings.ARGO_RECONCILE_WEBHOOK_URL = "http://argo-events/reconcile"
    now = timezone.now()
    Build.objects.filter(pk=build.pk).update(started_at=now, execution_deadline_at=now - timedelta(seconds=1))
    argo, storage, cleaner, cleanup = Mock(), Mock(), Mock(), Mock()
    storage.read.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
    backend = ArgoBuildBackend(client=argo, storage=storage)
    monkeypatch.setattr("infrastructure.execution.build_backend", lambda _: backend)
    monkeypatch.setattr("apps.deployment.builds.cleanup.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.deployment.execution.argo_recovery.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.deployment.builds.cleanup.BuildImageCleaner", lambda: cleaner)
    monkeypatch.setattr(cleanup_failed_build_artifacts, "delay", cleanup)

    _reconcile_argo_deadlines()
    build.refresh_from_db()
    assert build.status == "building"
    assert build.callback_wait_until > now
    cleanup.assert_not_called()
    Build.objects.filter(pk=build.pk).update(callback_wait_until=now - timedelta(seconds=1))

    with django_capture_on_commit_callbacks(execute=True):
        assert reconcile("build", str(build.public_id)) == "failed"
    build.refresh_from_db()
    assert build.status == "failed"
    assert build.execution_completed_at is None
    cleanup.assert_called_once_with(str(build.public_id), True)
    assert cleanup_failed_build_artifacts.run(str(build.public_id), True) == "waiting-for-execution"
    cleaner.delete.assert_not_called()
    storage.delete_prefix.assert_not_called()

    url = f"/internal/executions/build/{build.public_id}/stops/"
    token = argo.trigger.call_args.args[1]["callback_token"]
    client = APIClient()
    assert client.post(url, {"status": "stopped"}, format="json", HTTP_AUTHORIZATION="Bearer invalid").status_code == 403
    assert client.post(url, {"status": "error"}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 200
    build.refresh_from_db()
    assert build.argo_stop_confirmed_at is None
    cleanup.reset_mock()
    assert client.post(url, {"status": "stopped"}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 200
    cleanup.assert_called_once_with(str(build.public_id), True)
    assert cleanup_failed_build_artifacts.run(str(build.public_id)) == "purged"
    assert cleaner.delete.call_args.args[0].image_uri == expected_image(build)
    storage.delete_prefix.assert_called_once()
    build.refresh_from_db()
    assert build.execution_completed_at == build.argo_stop_confirmed_at
    assert build.next_execution_check_at is None


@pytest.fixture
def failed_deployment(project, monkeypatch):
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="sklearn", status="ready")
    deployment = Deployment.objects.create(version=version, build=build, backend="argo", status="failed")
    Endpoint.objects.create(deployment=deployment, public_url="https://example.test/model", runtime_name="deploy-x")
    for name in ("invalidate_model_server_cache", "append_deployment_log"):
        monkeypatch.setattr(f"apps.deployment.serving.rollout_tasks.{name}", Mock())
    return deployment


def report(deployment, phase):
    return APIClient().post(
        f"/internal/webhooks/deployments/{deployment.public_id}/",
        {"status": phase, "workflow_name": f"deploy-{deployment.public_id}"},
        format="json",
        HTTP_X_DEPLOYMENT_CALLBACK_TOKEN=issue_callback_token(deployment.public_id),
    )


def test_succeeded_callback_after_failure_removes_the_orphan_runtime(
    failed_deployment, monkeypatch, django_capture_on_commit_callbacks
):
    stop = Mock()
    monkeypatch.setattr("apps.deployment.serving.callbacks.stop_deployment.delay", stop)
    with django_capture_on_commit_callbacks(execute=True):
        assert report(failed_deployment, "Succeeded").data["duplicate"] is True
    stop.assert_called_once_with(str(failed_deployment.public_id))
    failed_deployment.refresh_from_db()
    assert failed_deployment.status == "failed"
    assert failed_deployment.deployed_at is None


def test_repeated_failure_callback_does_not_trigger_a_stop(
    failed_deployment, monkeypatch, django_capture_on_commit_callbacks
):
    stop = Mock()
    monkeypatch.setattr("apps.deployment.serving.callbacks.stop_deployment.delay", stop)
    with django_capture_on_commit_callbacks(execute=True):
        report(failed_deployment, "Failed")
    stop.assert_not_called()


def test_stopping_a_failed_deployment_removes_the_runtime_but_keeps_the_outcome(failed_deployment, monkeypatch):
    backend = Mock()
    backend.stop.return_value = {"confirmed": True}
    monkeypatch.setattr("apps.deployment.serving.rollout_tasks.deployment_backend", lambda _: backend)
    transition = Mock()
    monkeypatch.setattr("apps.deployment.serving.rollout_tasks.record_transition", transition)
    assert stop_deployment.run(str(failed_deployment.public_id)) == "failed"
    backend.stop.assert_called_once()
    failed_deployment.refresh_from_db()
    assert failed_deployment.status == "failed"
    assert failed_deployment.stopped_at is not None
    transition.assert_not_called()
