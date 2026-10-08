import secrets
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.services.callbacks import issue_callback_token
from apps.deployment.services.deployments import request_stop
from apps.deployment.tasks import _mark_deployment_succeeded, stop_deployment
from apps.registry.models import ModelVersion


@pytest.fixture
def runtimes(db, settings, monkeypatch):
    settings.CONTROL_PLANE_WEBHOOK_SECRET = secrets.token_urlsafe(48)
    owner = get_user_model().objects.create_user("stop-race@example.com", "test-password")
    project = ModelProject.objects.create(owner=owner, name="stop race")
    v1 = ModelVersion.objects.create(project=project, version="1")
    v2 = ModelVersion.objects.create(project=project, version="2")
    running = Deployment.objects.create(
        version=v1,
        build=Build.objects.create(project=project, version=v1, flavor="sklearn", status="ready"),
        backend="argo",
        status="succeeded",
    )
    candidate = Deployment.objects.create(
        version=v2,
        build=Build.objects.create(project=project, version=v2, flavor="sklearn", status="ready"),
        backend="argo",
        status="deploying",
    )
    for deployment in (running, candidate):
        Endpoint.objects.create(deployment=deployment, runtime_name=f"runtime-{deployment.pk}", health_status="healthy")
    project.active_deployment = running
    project.save(update_fields=["active_deployment"])
    stops = []
    monkeypatch.setattr("apps.deployment.tasks.stop_deployment.delay", stops.append)
    for module in ("apps.deployment.tasks", "apps.deployment.api.webhooks"):
        for name in ("invalidate_model_server_cache", "append_deployment_log", "enqueue_event"):
            monkeypatch.setattr(f"{module}.{name}", Mock())
    return project, running, candidate, stops


def test_stopping_a_deploying_candidate_blocks_late_promotion(runtimes, django_capture_on_commit_callbacks):
    project, running, candidate, stops = runtimes
    with django_capture_on_commit_callbacks(execute=True):
        assert request_stop(candidate).status == "stopped"
    assert stops == [str(candidate.public_id)]

    # Readiness arrives after the stop was claimed: the Running version must survive.
    assert _mark_deployment_succeeded(candidate) is False
    project.refresh_from_db()
    running.refresh_from_db()
    candidate.refresh_from_db()
    assert project.active_deployment_id == running.pk
    assert running.status == "succeeded"
    assert candidate.status == "stopped"
    assert stops == [str(candidate.public_id)]


def test_stopping_the_running_deployment_clears_it_before_the_runtime_stops(
    runtimes, django_capture_on_commit_callbacks
):
    project, running, _candidate, stops = runtimes
    with django_capture_on_commit_callbacks(execute=True):
        request_stop(running)
    project.refresh_from_db()
    running.refresh_from_db()
    assert project.active_deployment_id is None
    assert running.status == "stopped" and running.stopped_at is None
    assert running.endpoint.health_status == "unknown"
    assert stops == [str(running.public_id)]


def test_stop_keeps_failure_status(runtimes, django_capture_on_commit_callbacks):
    _project, _running, candidate, stops = runtimes
    Deployment.objects.filter(pk=candidate.pk).update(status="failed")
    candidate.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        assert request_stop(candidate).status == "failed"
    assert stops == [str(candidate.public_id)]


def test_promotion_claims_the_replaced_deployment_stop(runtimes, django_capture_on_commit_callbacks):
    project, running, candidate, stops = runtimes
    with django_capture_on_commit_callbacks(execute=True):
        assert _mark_deployment_succeeded(candidate) is True
    running.refresh_from_db()
    project.refresh_from_db()
    assert project.active_deployment_id == candidate.pk
    assert running.status == "stopped"
    assert stops == [str(running.public_id)]


def test_stop_task_records_runtime_stop_after_backend(runtimes, monkeypatch):
    project, running, _candidate, _stops = runtimes
    backend = Mock()
    monkeypatch.setattr("apps.deployment.tasks.deployment_backend", lambda _: backend)
    assert stop_deployment.run(str(running.public_id)) == "stopped"
    backend.stop.assert_called_once()
    project.refresh_from_db()
    running.refresh_from_db()
    assert project.active_deployment_id is None
    assert running.status == "stopped" and running.stopped_at is not None


def test_late_argo_success_for_stopped_deployment_removes_runtime_again(
    runtimes, django_capture_on_commit_callbacks
):
    project, running, candidate, stops = runtimes
    with django_capture_on_commit_callbacks(execute=True):
        request_stop(candidate)
        response = APIClient().post(
            f"/internal/webhooks/deployments/{candidate.public_id}/",
            {"status": "Succeeded", "workflow_name": "deploy-model-job-test"},
            format="json",
            HTTP_X_DEPLOYMENT_CALLBACK_TOKEN=issue_callback_token(candidate.public_id),
        )
    assert response.data == {"status": "stopped", "duplicate": True}
    assert stops == [str(candidate.public_id), str(candidate.public_id)]
    project.refresh_from_db()
    assert project.active_deployment_id == running.pk


def _age(deployment, seconds):
    from datetime import timedelta

    from django.utils import timezone

    Deployment.objects.filter(pk=deployment.pk).update(updated_at=timezone.now() - timedelta(seconds=seconds))


def test_reconcile_redispatches_stop_whose_runtime_removal_was_lost(runtimes, settings):
    from django.core.cache import cache

    from apps.deployment.tasks import reconcile_stopped_deployments

    cache.clear()
    _project, running, candidate, stops = runtimes
    Deployment.objects.filter(pk=running.pk).update(status="stopped")
    Deployment.objects.filter(pk=candidate.pk).update(status="stopped")
    _age(running, settings.STOP_RECONCILE_GRACE_SECONDS + 5)

    assert reconcile_stopped_deployments() == 1
    # Within the same grace period a still-failing stop is not hammered again.
    assert reconcile_stopped_deployments() == 0
    # The recently stopped candidate is left to its own in-flight task.
    assert stops == [str(running.public_id)]


def test_reconcile_ignores_completed_and_live_deployments(runtimes, settings):
    from django.core.cache import cache
    from django.utils import timezone

    from apps.deployment.tasks import reconcile_stopped_deployments

    cache.clear()
    _project, running, candidate, stops = runtimes
    Deployment.objects.filter(pk=running.pk).update(status="stopped", stopped_at=timezone.now())
    _age(running, settings.STOP_RECONCILE_GRACE_SECONDS + 5)
    _age(candidate, settings.STOP_RECONCILE_GRACE_SECONDS + 5)  # still deploying

    assert reconcile_stopped_deployments() == 0
    assert stops == []


def test_reconcile_is_scheduled():
    from django.conf import settings

    entry = settings.CELERY_BEAT_SCHEDULE["stopped-deployment-reconcile"]
    assert entry["task"] == "apps.deployment.tasks.reconcile_stopped_deployments"
