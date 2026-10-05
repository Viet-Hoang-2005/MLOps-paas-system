import json
import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.services.runtime_health import dispatch_health_checks, effective_health, probe_running_health
from apps.deployment.tasks import _mark_deployment_succeeded
from apps.registry.models import ModelVersion
from infrastructure.runtime_health import RuntimeHealthProbe


@pytest.fixture
def runtime(db):
    owner = get_user_model().objects.create_user("health@example.com", "test-password")
    project = ModelProject.objects.create(owner=owner, name="health")
    version = ModelVersion.objects.create(project=project, version="1", flavor="xgboost")
    build = Build.objects.create(project=project, version=version, status="ready", registration_status="registered")
    deployment = Deployment.objects.create(version=version, build=build, status="succeeded")
    project.active_deployment = deployment
    project.save(update_fields=["active_deployment"])
    endpoint = Endpoint.objects.create(deployment=deployment, public_url="http://gateway.test",
        internal_url="http://runtime:5001", health_status="healthy", last_checked_at=timezone.now() - timedelta(seconds=20))
    return project, deployment, endpoint


def claim(endpoint):
    token = uuid.uuid4()
    endpoint.health_check_token = token
    endpoint.health_check_lease_until = timezone.now() + timedelta(seconds=30)
    endpoint.save(update_fields=["health_check_token", "health_check_lease_until"])
    return str(token)


def test_scan_claims_once_and_enqueues_after_commit(runtime, monkeypatch, django_capture_on_commit_callbacks):
    _, deployment, endpoint = runtime
    enqueue = Mock()
    monkeypatch.setattr("apps.deployment.health_tasks.probe_runtime_health.apply_async", enqueue)
    with django_capture_on_commit_callbacks(execute=True):
        assert dispatch_health_checks() == 1
        enqueue.assert_not_called()
    endpoint.refresh_from_db()
    enqueue.assert_called_once_with(args=[str(deployment.public_id), str(endpoint.health_check_token)],
        queue="runtime-health", expires=15)
    assert dispatch_health_checks() == 0


def test_failed_publish_releases_lease_without_marking_runtime_unhealthy(runtime, monkeypatch, django_capture_on_commit_callbacks):
    _, _, endpoint = runtime
    monkeypatch.setattr("apps.deployment.health_tasks.probe_runtime_health.apply_async", Mock(side_effect=RuntimeError("broker down")))
    with django_capture_on_commit_callbacks(execute=True):
        dispatch_health_checks()
    endpoint.refresh_from_db()
    assert endpoint.health_check_token is None
    assert endpoint.health_status == "healthy"


def test_health_failure_and_recovery_preserve_lifecycle_and_running(runtime):
    project, deployment, endpoint = runtime
    for health in ("unhealthy", "healthy"):
        token = claim(endpoint)
        assert probe_running_health(str(deployment.public_id), token, Mock(check=Mock(return_value=health))) == health
        deployment.refresh_from_db()
        project.refresh_from_db()
        endpoint.refresh_from_db()
        assert deployment.status == "succeeded"
        assert project.active_deployment_id == deployment.pk
        assert endpoint.health_status == health
        assert endpoint.health_check_token is None
        assert probe_running_health(str(deployment.public_id), token, Mock()) == "ignored"


@pytest.mark.parametrize("change", ["stop", "replace", "expire", "new-token", "inactive"])
def test_late_probe_cannot_write_after_state_changed(runtime, change):
    project, deployment, endpoint = runtime
    token = claim(endpoint)
    previous_checked = endpoint.last_checked_at

    def check(**kwargs):
        if change == "stop":
            Deployment.objects.filter(pk=deployment.pk).update(status="stopped")
            Endpoint.objects.filter(pk=endpoint.pk).update(health_status="unknown", last_checked_at=None)
        elif change == "replace":
            new = Deployment.objects.create(version=deployment.version, build=deployment.build, status="succeeded")
            ModelProject.objects.filter(pk=project.pk).update(active_deployment=new)
        elif change == "expire":
            Endpoint.objects.filter(pk=endpoint.pk).update(health_check_lease_until=timezone.now() - timedelta(seconds=1))
        elif change == "new-token":
            Endpoint.objects.filter(pk=endpoint.pk).update(health_check_token=uuid.uuid4())
        else:
            ModelProject.objects.filter(pk=project.pk).update(is_active=False)
        return "unhealthy"

    assert probe_running_health(str(deployment.public_id), token, Mock(check=check)) == "ignored"
    endpoint.refresh_from_db()
    assert endpoint.health_status == ("unknown" if change == "stop" else "healthy")
    assert endpoint.last_checked_at == (None if change == "stop" else previous_checked)


def test_expired_lease_reclaimed_and_old_delivery_does_not_probe(runtime, monkeypatch):
    _, deployment, endpoint = runtime
    token = claim(endpoint)
    Endpoint.objects.filter(pk=endpoint.pk).update(health_check_lease_until=timezone.now() - timedelta(seconds=1))
    probe = Mock()
    assert probe_running_health(str(deployment.public_id), token, probe) == "ignored"
    probe.check.assert_not_called()
    monkeypatch.setattr("apps.deployment.health_tasks.probe_runtime_health.apply_async", Mock())
    assert dispatch_health_checks() == 1
    endpoint.refresh_from_db()
    assert str(endpoint.health_check_token) != token


def test_monitor_infrastructure_error_leaves_observation_untouched(runtime):
    _, deployment, endpoint = runtime
    token = claim(endpoint)
    old = endpoint.last_checked_at
    with pytest.raises(RuntimeError, match="monitor failed"):
        probe_running_health(str(deployment.public_id), token, Mock(check=Mock(side_effect=RuntimeError("monitor failed"))))
    endpoint.refresh_from_db()
    assert endpoint.health_status == "healthy" and endpoint.last_checked_at == old
    assert effective_health(endpoint, old + timedelta(seconds=46)) == "unknown"


def test_api_reads_saved_health_and_is_tenant_scoped(runtime, monkeypatch):
    project, _, endpoint = runtime
    monkeypatch.setattr(RuntimeHealthProbe, "check", Mock(side_effect=AssertionError("API must not probe")))
    client = APIClient()
    client.force_authenticate(project.owner)
    url = f"/api/models/{project.public_id}/"
    result = client.get(url)
    assert result.data["active_endpoint"]["registration_status"] == "registered"
    assert result.data["active_endpoint"]["health_status"] == "healthy"
    Endpoint.objects.filter(pk=endpoint.pk).update(last_checked_at=timezone.now() - timedelta(seconds=46))
    assert client.get(url).data["active_endpoint"]["health_status"] == "unknown"
    other = get_user_model().objects.create_user("other-health@example.com", "test-password")
    client.force_authenticate(other)
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("status", ["failed", "stopped"])
def test_readiness_and_delayed_completion_cannot_revive_terminal_deployment(runtime, status):
    _, deployment, _ = runtime
    Deployment.objects.filter(pk=deployment.pk).update(status=status)
    assert _mark_deployment_succeeded(deployment) is False
    deployment.refresh_from_db()
    assert deployment.status == status


def test_schema_rejects_mixed_lifecycle_and_health(runtime):
    _, deployment, endpoint = runtime
    with pytest.raises(IntegrityError), transaction.atomic():
        Deployment.objects.filter(pk=deployment.pk).update(status="healthy")
    with pytest.raises(IntegrityError), transaction.atomic():
        Endpoint.objects.filter(pk=endpoint.pk).update(health_status="stopped")


def test_scheduler_uses_only_health_queue_and_bounded_tasks(settings):
    from apps.deployment.health_tasks import probe_runtime_health

    assert len(settings.CELERY_BEAT_SCHEDULE) == 1
    schedule = settings.CELERY_BEAT_SCHEDULE["runtime-health-scan"]
    assert schedule["schedule"] == 15
    assert schedule["options"] == {"queue": "runtime-health", "expires": 15}
    assert probe_runtime_health.time_limit == 10
    assert probe_runtime_health.soft_time_limit == 8


def fake_response(monkeypatch, body=None, status_code=200, error=None):
    response = Mock(status_code=status_code)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.iter_content.return_value = [body if isinstance(body, bytes) else json.dumps(body).encode()]
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    session.request = Mock(return_value=response, side_effect=error)
    monkeypatch.setattr("infrastructure.runtime_health.requests.Session", lambda: session)
    return session


@pytest.mark.parametrize("flavor,method", [("xgboost", "GET"), ("sklearn", "GET"), ("pytorch", "POST"), ("tensorflow", "POST")])
def test_probe_method_identity_and_network_bounds(monkeypatch, flavor, method):
    session = fake_response(monkeypatch, {"status": "healthy", "model_loaded": True, "project_id": "p", "model_version_id": "v"})
    assert RuntimeHealthProbe().check(url="http://runtime/", flavor=flavor, project_id="p", version_id="v") == "healthy"
    session.request.assert_called_once_with(method, "http://runtime/health", timeout=(1, 2), allow_redirects=False,
        stream=True, **({"json": {}} if method == "POST" else {}))
    assert session.trust_env is False


@pytest.mark.parametrize("body,status,error", [
    ({"status": "healthy", "model_loaded": True, "project_id": "other", "model_version_id": "v"}, 200, None),
    ({"status": "healthy", "model_loaded": False, "project_id": "p", "model_version_id": "v"}, 200, None),
    ({"status": "healthy", "model_loaded": True, "project_id": "p", "model_version_id": "old"}, 200, None),
    ([], 200, None), (b"invalid json", 200, None), (b"x" * 65537, 200, None),
    ({}, 503, None), ({}, 302, None), ({}, 200, requests.Timeout()), ({}, 200, requests.ConnectionError()),
], ids=["wrong-project", "not-loaded", "wrong-version", "array", "invalid-json", "too-large", "http-error", "redirect", "timeout", "connection-error"])
def test_invalid_or_unreachable_runtime_is_unhealthy(monkeypatch, body, status, error):
    fake_response(monkeypatch, body, status, error)
    assert RuntimeHealthProbe().check(url="http://runtime", flavor="xgboost", project_id="p", version_id="v") == "unhealthy"


def test_missing_internal_url_is_unknown():
    assert RuntimeHealthProbe().check(url="", flavor="xgboost", project_id="p", version_id="v") == "unknown"


def test_duplicate_delivery_cannot_probe_while_original_is_in_flight(runtime):
    _, deployment, endpoint = runtime
    token = claim(endpoint)
    duplicate_probe = Mock()

    def check(**kwargs):
        assert probe_running_health(str(deployment.public_id), token, duplicate_probe) == "ignored"
        return "healthy"

    assert probe_running_health(str(deployment.public_id), token, Mock(check=check)) == "healthy"
    duplicate_probe.check.assert_not_called()


def test_readiness_timeout_fails_candidate_and_preserves_running(runtime, monkeypatch):
    project, running, _ = runtime
    candidate = Deployment.objects.create(version=running.version, build=running.build, status="deploying")
    Endpoint.objects.create(deployment=candidate, public_url="http://candidate")
    monkeypatch.setattr("apps.deployment.tasks.deployment_backend", lambda _: Mock(health=Mock(return_value=(False, {}))))
    for name in ("invalidate_model_server_cache", "append_deployment_log"):
        monkeypatch.setattr(f"apps.deployment.tasks.{name}", Mock())
    from apps.deployment.services.local_execution import check_execution
    token = uuid.uuid4()
    Deployment.objects.filter(pk=candidate.pk).update(
        execution_check_token=token, execution_check_lease_until=timezone.now() + timedelta(seconds=30),
        execution_deadline_at=timezone.now() - timedelta(seconds=1),
    )
    assert check_execution("deploy", str(candidate.public_id), str(token), inspector=Mock(return_value=Mock(
        attrs={"State": {"Status": "running"}})), remover=Mock()) == "waiting"
    project.refresh_from_db()
    candidate.refresh_from_db()
    assert project.active_deployment_id == running.pk
    assert candidate.status == "failed"


def test_stop_clears_health_and_scan_selection(runtime, monkeypatch):
    from apps.deployment.tasks import stop_deployment

    project, deployment, endpoint = runtime
    claim(endpoint)
    monkeypatch.setattr("apps.deployment.tasks.deployment_backend", lambda _: Mock())
    for name in ("invalidate_model_server_cache", "append_deployment_log"):
        monkeypatch.setattr(f"apps.deployment.tasks.{name}", Mock())
    assert stop_deployment.run(str(deployment.public_id)) == "stopped"
    endpoint.refresh_from_db()
    project.refresh_from_db()
    assert endpoint.health_status == "unknown"
    assert endpoint.last_checked_at is None and endpoint.health_check_token is None
    assert project.active_deployment_id is None
    assert dispatch_health_checks() == 0
