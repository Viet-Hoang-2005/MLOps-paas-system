import uuid
from datetime import timedelta
from unittest.mock import Mock

import docker.errors
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.services.local_execution import check_execution, dispatch_execution_checks
from infrastructure.execution.local_containers import ContainerOwnershipError, identity, owned_container, start_container

pytestmark = pytest.mark.django_db


@pytest.fixture
def attempt(monkeypatch):
    owner = get_user_model().objects.create_user("watch@example.com", "test-password")
    project = ModelProject.objects.create(owner=owner, name="watch project")
    build = Build.objects.create(project=project, flavor="xgboost", status="building", backend="docker",
        package_uri="s3://artifact-bucket/build/package.zip", external_build_id="container",
        execution_deadline_at=timezone.now() + timedelta(hours=12), next_execution_check_at=timezone.now())
    for path in ("apps.deployment.tasks.invalidate_model_server_cache", "apps.deployment.tasks.append_deployment_log",
        "apps.deployment.services.local_execution.append_deployment_log", "apps.deployment.tasks.cleanup_failed_build_artifacts.delay"):
        monkeypatch.setattr(path, Mock())
    return build


def claim(row):
    token = uuid.uuid4()
    type(row).objects.filter(pk=row.pk).update(execution_check_token=token,
        execution_check_lease_until=timezone.now() + timedelta(seconds=30))
    return str(token)


def container(status="running", exit_code=0):
    return Mock(attrs={"State": {"Status": status, "ExitCode": exit_code}}, logs=Mock(return_value=b"runner log"))


def check(row, kind="build", status="running", exit_code=0, **kwargs):
    return check_execution(kind, str(row.public_id), claim(row), inspector=Mock(return_value=container(status, exit_code)),
        remover=Mock(), **kwargs)


def test_scan_routes_only_docker_and_recovers_after_expired_lease(attempt, monkeypatch, django_capture_on_commit_callbacks):
    enqueue = Mock()
    monkeypatch.setattr("apps.deployment.execution_tasks.check_local_execution.apply_async", enqueue)
    Build.objects.create(project=attempt.project, flavor="xgboost", backend="argo", next_execution_check_at=timezone.now())
    with django_capture_on_commit_callbacks(execute=True):
        assert dispatch_execution_checks() == 1
        assert dispatch_execution_checks() == 0
    assert enqueue.call_args.kwargs["queue"] == "celery"
    assert enqueue.call_args.kwargs["expires"] == 10
    Build.objects.filter(pk=attempt.pk).update(execution_check_lease_until=timezone.now() - timedelta(seconds=1))
    with django_capture_on_commit_callbacks(execute=True):
        assert dispatch_execution_checks() == 1


def test_publish_failure_releases_lease(attempt, monkeypatch, django_capture_on_commit_callbacks):
    monkeypatch.setattr("apps.deployment.execution_tasks.check_local_execution.apply_async", Mock(side_effect=RuntimeError("broker")))
    with django_capture_on_commit_callbacks(execute=True):
        dispatch_execution_checks()
    attempt.refresh_from_db()
    assert attempt.execution_check_token is None
    assert attempt.status == "building"


def test_build_does_not_become_ready_from_exit_zero(attempt):
    assert check(attempt, status="exited") == "waiting"
    attempt.refresh_from_db()
    assert attempt.status == "building"
    assert attempt.callback_wait_until is not None
    Build.objects.filter(pk=attempt.pk).update(callback_wait_until=timezone.now() - timedelta(seconds=1))
    assert check(attempt, status="exited") == "failed"
    attempt.refresh_from_db()
    assert "callback" in attempt.error_message


@pytest.mark.parametrize("reason", ["nonzero", "deadline", "missing"])
def test_build_failure_states(attempt, reason):
    inspector = Mock(return_value=container("exited", 1))
    if reason == "deadline":
        Build.objects.filter(pk=attempt.pk).update(execution_deadline_at=timezone.now() - timedelta(seconds=1))
        inspector.return_value = container()
    if reason == "missing":
        inspector.side_effect = docker.errors.NotFound("gone")
    assert check_execution("build", str(attempt.public_id), claim(attempt), inspector=inspector, remover=Mock()) == "failed"
    attempt.refresh_from_db()
    assert attempt.status == "failed"


def test_monitor_outage_retries_without_fabricating_model_failure(attempt):
    assert check_execution("build", str(attempt.public_id), claim(attempt),
        inspector=Mock(side_effect=RuntimeError("Docker unavailable"))) == "retry"
    attempt.refresh_from_db()
    assert attempt.status == "building"
    assert attempt.next_execution_check_at is not None


def test_duplicate_delivery_is_single_use(attempt):
    token = claim(attempt)
    nested_inspector = Mock()
    def inspect(row, kind):
        assert check_execution(kind, str(row.public_id), token, inspector=nested_inspector) == "ignored"
        return container()
    check_execution("build", str(attempt.public_id), token, inspector=inspect, remover=Mock())
    nested_inspector.assert_not_called()


def test_callback_wins_race_with_failed_observation(attempt):
    def inspect(row, kind):
        Build.objects.filter(pk=row.pk).update(status="ready")
        return container("exited", 1)
    assert check_execution("build", str(attempt.public_id), claim(attempt), inspector=inspect, remover=Mock()) == "ready"
    attempt.refresh_from_db()
    assert attempt.status == "ready"


def test_success_callback_is_validated_idempotent_and_cannot_revive_failure(attempt, settings):
    settings.CONTROL_PLANE_WEBHOOK_SECRET = "fixture-callback-secret"
    client = APIClient()
    url = f"/internal/webhooks/builds/{attempt.public_id}/"
    headers = {"HTTP_X_CONTROL_PLANE_SECRET": settings.CONTROL_PLANE_WEBHOOK_SECRET}
    assert client.post(url, {"status": "success"}, format="json", **headers).status_code == 400
    payload = {"status": "success", "image_uri": f"image-{attempt.project.public_id}:build-{attempt.public_id}",
        "image_digest": "sha256:" + "a" * 64, "package_manifest": {"format": "mlflow"}}
    assert client.post(url, payload, format="json", **headers).status_code == 200
    assert client.post(url, {"status": "error"}, format="json", **headers).data["duplicate"] is True
    attempt.refresh_from_db()
    assert attempt.status == "ready"
    assert attempt.version_id is None
    Build.objects.filter(pk=attempt.pk).update(status="failed")
    assert client.post(url, payload, format="json", **headers).data["duplicate"] is True
    attempt.refresh_from_db()
    assert attempt.status == "failed"


def test_ready_build_waits_for_runner_exit_before_cleanup(attempt):
    Build.objects.filter(pk=attempt.pk).update(status="ready")
    remove = Mock()
    check_execution("build", str(attempt.public_id), claim(attempt), inspector=Mock(return_value=container()), remover=remove)
    remove.assert_not_called()
    attempt.refresh_from_db()
    assert attempt.next_execution_check_at is not None
    check_execution("build", str(attempt.public_id), claim(attempt), inspector=Mock(return_value=container("exited")), remover=remove)
    remove.assert_called_once()
    attempt.refresh_from_db()
    assert attempt.next_execution_check_at is None
    assert attempt.logs == "runner log"


@pytest.fixture
def candidate(attempt):
    from apps.registry.models import ModelVersion
    version = ModelVersion.objects.create(project=attempt.project, version="1", flavor="xgboost")
    row = Deployment.objects.create(build=attempt, version=version, backend="docker", status="deploying",
        external_deployment_id="runtime", execution_deadline_at=timezone.now() + timedelta(seconds=90))
    Endpoint.objects.create(deployment=row, public_url="http://gateway", internal_url="http://runtime:5001")
    return row


def test_readiness_success_updates_running_not_registration(candidate):
    assert check(candidate, kind="deploy", probe=Mock(check=Mock(return_value="healthy"))) == "succeeded"
    candidate.refresh_from_db()
    candidate.version.project.refresh_from_db()
    assert candidate.status == "succeeded"
    assert candidate.next_execution_check_at is None
    assert candidate.version.project.active_deployment_id == candidate.pk


def test_unhealthy_readiness_waits_without_changing_old_running(candidate):
    assert check(candidate, kind="deploy", probe=Mock(check=Mock(return_value="unhealthy"))) == "waiting"
    candidate.refresh_from_db()
    assert candidate.status == "deploying"
    assert candidate.next_execution_check_at is not None


def test_stop_during_probe_cannot_resurrect_runtime(candidate):
    def probe(**kwargs):
        Deployment.objects.filter(pk=candidate.pk).update(status="stopped")
        return "healthy"
    assert check(candidate, kind="deploy", probe=Mock(check=probe)) == "cancelled"
    candidate.refresh_from_db()
    assert candidate.status == "stopped"
    assert candidate.version.project.active_deployment_id is None


def test_late_probe_after_deadline_cannot_succeed(candidate):
    def probe(**kwargs):
        Deployment.objects.filter(pk=candidate.pk).update(execution_deadline_at=timezone.now() - timedelta(seconds=1))
        return "healthy"
    check(candidate, kind="deploy", probe=Mock(check=probe))
    candidate.refresh_from_db()
    assert candidate.status == "failed"


def test_start_redelivery_reuses_owned_attempt(attempt):
    existing = container()
    existing.id = "container"
    existing.attrs["Config"] = {"Labels": identity(attempt, "build")}
    client = Mock()
    client.containers.get.return_value = existing
    docker_client = Mock(client=client)
    assert start_container(docker_client, attempt, "build", name=f"build-{attempt.public_id}") is existing
    docker_client.run.assert_not_called()


def test_foreign_container_is_never_removed_or_reused(attempt):
    existing = container()
    existing.id = "container"
    existing.attrs["Config"] = {"Labels": {"mlops_tenant_id": "other"}}
    client = Mock()
    client.containers.get.return_value = existing
    with pytest.raises(ContainerOwnershipError):
        owned_container(client, attempt, "build")
    existing.remove.assert_not_called()


def test_lease_expiry_discards_inflight_result(candidate):
    def probe(**kwargs):
        Deployment.objects.filter(pk=candidate.pk).update(execution_check_lease_until=timezone.now() - timedelta(seconds=1))
        return "healthy"
    assert check(candidate, kind="deploy", probe=Mock(check=probe)) == "ignored"
    candidate.refresh_from_db()
    assert candidate.status == "deploying"


def test_cancelled_build_cleanup_is_dispatched_only_after_runner_stops(attempt, monkeypatch, django_capture_on_commit_callbacks):
    Build.objects.filter(pk=attempt.pk).update(status="cancelled")
    cleanup = Mock()
    remove = Mock()
    monkeypatch.setattr("apps.deployment.tasks.cleanup_failed_build_artifacts.delay", cleanup)
    with django_capture_on_commit_callbacks(execute=True):
        assert check_execution("build", str(attempt.public_id), claim(attempt),
            inspector=Mock(return_value=container()), remover=remove) == "cancelled"
    remove.assert_called_once()
    cleanup.assert_called_once_with(str(attempt.public_id), True)
    attempt.refresh_from_db()
    assert attempt.next_execution_check_at is None


def test_dispatch_error_without_recorded_id_still_waits_for_producer_cleanup(attempt, monkeypatch):
    from apps.deployment.tasks import cleanup_failed_build_artifacts

    Build.objects.filter(pk=attempt.pk).update(status="failed", external_build_id="")
    cleaner = Mock()
    monkeypatch.setattr("apps.deployment.tasks.BuildImageCleaner", cleaner)
    assert cleanup_failed_build_artifacts.run(str(attempt.public_id), True) == "waiting-for-execution"
    cleaner.assert_not_called()
    assert check_execution("build", str(attempt.public_id), claim(attempt),
        inspector=Mock(side_effect=docker.errors.NotFound("never started")), remover=Mock()) == "failed"
    attempt.refresh_from_db()
    assert attempt.next_execution_check_at is None


def test_redelivery_keeps_deadline_from_first_container_creation(candidate):
    first_creation = timezone.now() - timedelta(seconds=60)
    existing = container()
    existing.id = "runtime"
    existing.attrs["Created"] = first_creation.isoformat()
    existing.attrs["Config"] = {"Labels": identity(candidate, "deploy")}
    Deployment.objects.filter(pk=candidate.pk).update(external_deployment_id="", execution_deadline_at=None)
    candidate.refresh_from_db()
    client = Mock()
    client.containers.get.return_value = existing
    docker_client = Mock(client=client)
    start_container(docker_client, candidate, "deploy", name=f"deploy-{candidate.public_id}")
    candidate.refresh_from_db()
    assert candidate.execution_deadline_at == first_creation + timedelta(seconds=90)
    docker_client.run.assert_not_called()


def test_recorded_missing_container_is_not_recreated(attempt):
    docker_client = Mock()
    docker_client.client.containers.get.side_effect = docker.errors.NotFound("gone")
    with pytest.raises(RuntimeError, match="new attempt"):
        start_container(docker_client, attempt, "build")
    docker_client.run.assert_not_called()


def test_cleanup_publish_failure_keeps_watch_recoverable(attempt, monkeypatch, django_capture_on_commit_callbacks):
    Build.objects.filter(pk=attempt.pk).update(status="failed")
    monkeypatch.setattr("apps.deployment.tasks.cleanup_failed_build_artifacts.delay", Mock(side_effect=RuntimeError("broker unavailable")))
    with django_capture_on_commit_callbacks(execute=True):
        assert check(attempt, status="exited") == "failed"
    attempt.refresh_from_db()
    assert attempt.next_execution_check_at is not None
    assert attempt.execution_check_token is None


@pytest.mark.parametrize("change", ["image", "digest", "manifest", "identity", "deadline"])
def test_callback_rejects_invalid_success_metadata_or_expired_deadline(attempt, settings, change):
    settings.CONTROL_PLANE_WEBHOOK_SECRET = "fixture-callback-secret"
    payload = {"status": "success", "image_uri": f"image-{attempt.project.public_id}:build-{attempt.public_id}",
        "image_digest": "sha256:" + "a" * 64, "package_manifest": {"format": "mlflow"}}
    if change == "image":
        payload["image_uri"] = "image-other:build-other"
    elif change == "digest":
        payload["image_digest"] = ""
    elif change == "manifest":
        payload["package_manifest"] = {}
    elif change == "identity":
        payload["build_id"] = str(uuid.uuid4())
    else:
        Build.objects.filter(pk=attempt.pk).update(execution_deadline_at=timezone.now() - timedelta(seconds=1))
    response = APIClient().post(f"/internal/webhooks/builds/{attempt.public_id}/", payload, format="json",
        HTTP_X_CONTROL_PLANE_SECRET=settings.CONTROL_PLANE_WEBHOOK_SECRET)
    assert response.status_code == (409 if change == "deadline" else 400)
    attempt.refresh_from_db()
    assert attempt.status == "building"
