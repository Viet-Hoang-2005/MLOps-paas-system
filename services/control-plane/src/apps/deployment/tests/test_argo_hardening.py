"""Argo build webhook trust, build cancellation and failed-deployment runtime cleanup."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.services.callbacks import issue_callback_token
from apps.deployment.tasks import cancel_build, stop_deployment
from apps.registry.models import ModelVersion
from infrastructure.execution.argo_backends import ArgoBuildBackend
from infrastructure.execution.image_references import temporary_image_reference

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
    monkeypatch.setattr("apps.deployment.api.webhooks.complete_build", complete)
    assert post_build(build, **success_payload(build, **overrides)).status_code == 400
    complete.assert_not_called()
    build.refresh_from_db()
    assert build.status == "building"


def test_argo_success_registers_only_the_build_scoped_image(build, monkeypatch):
    complete = Mock(side_effect=lambda build, **kwargs: build)
    monkeypatch.setattr("apps.deployment.api.webhooks.complete_build", complete)
    assert post_build(build, **success_payload(build)).status_code == 200
    kwargs = complete.call_args.kwargs
    assert kwargs["image_uri"] == expected_image(build)
    assert kwargs["image_digest"] == DIGEST


def test_argo_failure_never_stores_a_reporter_chosen_image(build, monkeypatch):
    monkeypatch.setattr("apps.deployment.api.webhooks.cleanup_failed_build_artifacts.delay", Mock())
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


def test_late_callback_of_a_cancelled_argo_build_cleans_up_its_output(build, monkeypatch, django_capture_on_commit_callbacks):
    Build.objects.filter(pk=build.pk).update(status="cancelled")
    cleanup = Mock()
    monkeypatch.setattr("apps.deployment.api.webhooks.cleanup_failed_build_artifacts.delay", cleanup)
    with django_capture_on_commit_callbacks(execute=True):
        response = post_build(build, **success_payload(build))
    assert response.data["duplicate"] is True
    build.refresh_from_db()
    assert build.status == "cancelled"
    assert build.image_uri == expected_image(build)
    cleanup.assert_called_once_with(str(build.public_id), True)


def test_argo_cancel_asks_the_cluster_to_terminate_the_build_workflow(build, settings):
    settings.ARGO_CANCEL_BUILD_WEBHOOK_URL = "http://argo-events/cancel-build"
    client = SimpleNamespace(trigger=Mock(return_value={"ok": True}))
    ArgoBuildBackend(client=client, storage=object()).cancel(build)
    url, payload = client.trigger.call_args.args
    assert url == "http://argo-events/cancel-build"
    assert payload == {
        "build_id": str(build.public_id),
        "project_id": str(build.project.public_id),
        "tenant_id": build.project.owner.tenant_id,
    }


def test_argo_cancel_is_a_noop_when_not_configured(build, settings):
    settings.ARGO_CANCEL_BUILD_WEBHOOK_URL = ""
    client = SimpleNamespace(trigger=Mock())
    assert ArgoBuildBackend(client=client, storage=object()).cancel(build) is None
    client.trigger.assert_not_called()


def test_cancel_task_retries_when_the_cluster_cannot_be_reached(build, monkeypatch):
    backend = Mock(cancel=Mock(side_effect=ConnectionError("argo-events down")))
    monkeypatch.setattr("apps.deployment.tasks.build_backend", lambda _: backend)
    cleanup = Mock()
    monkeypatch.setattr("apps.deployment.tasks.cleanup_failed_build_artifacts.delay", cleanup)
    assert cancel_build.autoretry_for == (Exception,)
    with pytest.raises(ConnectionError):
        cancel_build.run(str(build.public_id))
    cleanup.assert_not_called()


@pytest.fixture
def failed_deployment(project, monkeypatch):
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="sklearn", status="ready")
    deployment = Deployment.objects.create(version=version, build=build, backend="argo", status="failed")
    Endpoint.objects.create(deployment=deployment, public_url="https://example.test/model", runtime_name="deploy-x")
    for module in ("apps.deployment.tasks", "apps.deployment.api.webhooks"):
        for name in ("invalidate_model_server_cache", "append_deployment_log", "enqueue_event"):
            monkeypatch.setattr(f"{module}.{name}", Mock())
    return deployment


def report(deployment, phase):
    return APIClient().post(
        f"/internal/webhooks/deployments/{deployment.public_id}/",
        {"status": phase, "workflow_name": "deploy-model-job-test"},
        format="json",
        HTTP_X_DEPLOYMENT_CALLBACK_TOKEN=issue_callback_token(deployment.public_id),
    )


def test_succeeded_callback_after_failure_removes_the_orphan_runtime(
    failed_deployment, monkeypatch, django_capture_on_commit_callbacks
):
    stop = Mock()
    monkeypatch.setattr("apps.deployment.api.webhooks.stop_deployment.delay", stop)
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
    monkeypatch.setattr("apps.deployment.api.webhooks.stop_deployment.delay", stop)
    with django_capture_on_commit_callbacks(execute=True):
        report(failed_deployment, "Failed")
    stop.assert_not_called()


def test_stopping_a_failed_deployment_removes_the_runtime_but_keeps_the_outcome(failed_deployment, monkeypatch):
    backend = Mock()
    monkeypatch.setattr("apps.deployment.tasks.deployment_backend", lambda _: backend)
    transition = Mock()
    monkeypatch.setattr("apps.deployment.tasks.record_transition", transition)
    assert stop_deployment.run(str(failed_deployment.public_id)) == "failed"
    backend.stop.assert_called_once()
    failed_deployment.refresh_from_db()
    assert failed_deployment.status == "failed"
    assert failed_deployment.stopped_at is not None
    transition.assert_not_called()

