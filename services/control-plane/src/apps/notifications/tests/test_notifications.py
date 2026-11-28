import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.notifications.delivery import create_notification
from apps.notifications.models import Notification


def test_training_notification_targets_workspace_job_snapshot():
    from apps.notifications.events import notify_training_result

    job_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    job = SimpleNamespace(
        public_id=job_id,
        workspace=SimpleNamespace(public_id=workspace_id),
        owner=object(),
        status="completed",
        project_id=None,
    )
    with patch("apps.notifications.events.create_notification") as create:
        notify_training_result(job)
    assert create.call_count == 1
    values = create.call_args.kwargs
    assert values["link"] == f"/dashboard/training/workspaces/{workspace_id}/job/{job_id}"
    assert values["metadata"]["workspace_id"] == str(workspace_id)
    assert values["metadata"]["job_id"] == str(job_id)
    assert values["metadata"]["project_id"] is None


@pytest.mark.django_db
def test_create_and_query_notifications():
    user = get_user_model().objects.create_user("user1@example.com", "pass123")
    notification = create_notification(
        user=user,
        title="Training completed",
        message="Model trained successfully with accuracy 98%",
        type=Notification.Type.TRAINING,
        level=Notification.Level.SUCCESS,
        link="/dashboard/projects/1/training",
    )

    assert notification.public_id is not None
    assert notification.is_read is False
    assert notification.title == "Training completed"
    assert notification.user == user

    client = APIClient()
    client.force_authenticate(user)

    # 1. Test unread count endpoint
    unread_resp = client.get("/api/notifications/unread-count/")
    assert unread_resp.status_code == 200
    assert unread_resp.data["unread_count"] == 1

    # 2. Test list endpoint
    list_resp = client.get("/api/notifications/")
    assert list_resp.status_code == 200
    assert list_resp.data["count"] == 1
    assert list_resp.data["results"][0]["id"] == str(notification.public_id)

    # 3. Test mark as read endpoint
    read_resp = client.patch(f"/api/notifications/{notification.public_id}/read/")
    assert read_resp.status_code == 200
    assert read_resp.data["is_read"] is True

    unread_resp2 = client.get("/api/notifications/unread-count/")
    assert unread_resp2.data["unread_count"] == 0

    # 4. Test delete endpoint
    del_resp = client.delete(f"/api/notifications/{notification.public_id}/")
    assert del_resp.status_code == 204

    unread_resp3 = client.get("/api/notifications/unread-count/")
    assert unread_resp3.data["unread_count"] == 0


@pytest.mark.django_db
def test_notifications_tenant_isolation():
    user1 = get_user_model().objects.create_user("user1@example.com", "pass123")
    user2 = get_user_model().objects.create_user("user2@example.com", "pass123")

    notif1 = create_notification(user=user1, title="User1 Notif", message="Private message")
    notif2 = create_notification(user=user2, title="User2 Notif", message="Other message")

    client = APIClient()
    client.force_authenticate(user1)

    # user1 should only see their own notifications
    resp = client.get("/api/notifications/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["id"] == str(notif1.public_id)

    # user1 cannot mark user2's notification as read
    patch_resp = client.patch(f"/api/notifications/{notif2.public_id}/read/")
    assert patch_resp.status_code == 404

    # user1 cannot delete user2's notification
    del_resp = client.delete(f"/api/notifications/{notif2.public_id}/")
    assert del_resp.status_code == 404


@pytest.mark.django_db
def test_mark_all_notifications_as_read():
    user = get_user_model().objects.create_user("user@example.com", "pass123")
    create_notification(user=user, title="Msg 1", message="...")
    create_notification(user=user, title="Msg 2", message="...")

    client = APIClient()
    client.force_authenticate(user)

    assert client.get("/api/notifications/unread-count/").data["unread_count"] == 2

    post_resp = client.post("/api/notifications/mark-all-read/")
    assert post_resp.status_code == 200
    assert post_resp.data["updated"] == 2

    assert client.get("/api/notifications/unread-count/").data["unread_count"] == 0


@pytest.mark.django_db
def test_alertmanager_webhook_creates_notification():
    user = get_user_model().objects.create_user("owner@example.com", "pass123")
    project = ModelProject.objects.create(owner=user, name="CreditRisk")

    client = APIClient()
    secret = settings.CONTROL_PLANE_WEBHOOK_SECRET

    alert_payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighInferenceErrors",
                    "severity": "warning",
                    "project_id": str(project.public_id),
                    "model_version_id": str(uuid.uuid4()),
                },
                "annotations": {
                    "summary": "High Model Inference Errors",
                    "description": "Model endpoint is generating 6 errors/sec.",
                },
            }
        ],
    }

    # Should reject without secret
    resp_unauth = client.post("/internal/webhooks/alerts/", alert_payload, format="json")
    assert resp_unauth.status_code == 403

    # Should succeed with secret
    resp_auth = client.post(
        "/internal/webhooks/alerts/",
        alert_payload,
        format="json",
        HTTP_X_CONTROL_PLANE_SECRET=secret,
    )
    assert resp_auth.status_code == 200
    assert resp_auth.data["created_notifications"] == 1

    # Check that user received the alert notification
    client.force_authenticate(user)
    list_resp = client.get("/api/notifications/")
    assert list_resp.status_code == 200
    assert list_resp.data["count"] == 1
    item = list_resp.data["results"][0]
    assert item["type"] == "alert"
    assert item["level"] == "warning"
    assert "High Model Inference Errors" in item["title"]


@pytest.mark.django_db
def test_project_lifecycle_notifications():
    from apps.notifications.events import (
        notify_project_created,
        notify_project_deleted,
        notify_project_metadata_updated,
        notify_project_preview_updated,
    )

    user = get_user_model().objects.create_user("project_owner@example.com", "pass123")
    project = ModelProject.objects.create(
        owner=user,
        name="Test Fraud Model",
        description="Fraud detection model project",
    )

    notify_project_created(project)
    notify_project_metadata_updated(project)
    notify_project_preview_updated(project)
    notify_project_deleted(project)

    client = APIClient()
    client.force_authenticate(user)
    list_resp = client.get("/api/notifications/?type=project")
    assert list_resp.status_code == 200
    assert list_resp.data["count"] == 4

    titles = [item["title"] for item in list_resp.data["results"]]
    assert any("Model Project Created" in t for t in titles)
    assert any("Project Metadata Updated" in t for t in titles)
    assert any("Model Preview Updated" in t for t in titles)
    assert any("Model Project Deleted" in t for t in titles)


@pytest.mark.django_db
def test_alertmanager_webhook_dedupes_fingerprint_resets_on_resolved_and_checks_tenant():
    from django.core.cache import cache

    cache.clear()
    user = get_user_model().objects.create_user("dedupe-owner@example.com", "pass123")
    project = ModelProject.objects.create(owner=user, name="FraudShield")

    client = APIClient()
    secret = settings.CONTROL_PLANE_WEBHOOK_SECRET
    fp = "abc123fingerprint"

    def make_payload(alert_status="firing", tenant_id=None):
        labels = {
            "alertname": "HighInferenceLatency",
            "severity": "critical",
            "project_id": str(project.public_id),
        }
        if tenant_id is not None:
            labels["tenant_id"] = tenant_id
        return {
            "alerts": [
                {
                    "status": alert_status,
                    "fingerprint": fp,
                    "startsAt": "2026-11-27T08:00:00Z",
                    "labels": labels,
                    "annotations": {"summary": "Latency spike"},
                }
            ]
        }

    # Mismatched tenant_id must be rejected
    resp_wrong_tenant = client.post(
        "/internal/webhooks/alerts/",
        make_payload(tenant_id="T-wrong-tenant"),
        format="json",
        HTTP_X_CONTROL_PLANE_SECRET=secret,
    )
    assert resp_wrong_tenant.status_code == 200
    assert resp_wrong_tenant.data["created_notifications"] == 0

    # First firing with matching tenant_id creates 1 notification
    resp_first = client.post(
        "/internal/webhooks/alerts/",
        make_payload(tenant_id=user.tenant_id),
        format="json",
        HTTP_X_CONTROL_PLANE_SECRET=secret,
    )
    assert resp_first.status_code == 200
    assert resp_first.data["created_notifications"] == 1

    # Repeated firing within repeat_interval is deduplicated
    resp_repeat = client.post(
        "/internal/webhooks/alerts/",
        make_payload(tenant_id=user.tenant_id),
        format="json",
        HTTP_X_CONTROL_PLANE_SECRET=secret,
    )
    assert resp_repeat.status_code == 200
    assert resp_repeat.data["created_notifications"] == 0

    # Resolved clears dedupe so a later firing creates a new notification
    resp_resolved = client.post(
        "/internal/webhooks/alerts/",
        make_payload(alert_status="resolved", tenant_id=user.tenant_id),
        format="json",
        HTTP_X_CONTROL_PLANE_SECRET=secret,
    )
    assert resp_resolved.status_code == 200
    assert resp_resolved.data["created_notifications"] == 0

    # Mark existing notification read so DB unread check doesn't block re-firing after resolved
    Notification.objects.filter(user=user).update(is_read=True)

    resp_refire = client.post(
        "/internal/webhooks/alerts/",
        make_payload(tenant_id=user.tenant_id),
        format="json",
        HTTP_X_CONTROL_PLANE_SECRET=secret,
    )
    assert resp_refire.status_code == 200
    assert resp_refire.data["created_notifications"] == 1
    assert Notification.objects.filter(user=user, metadata__fingerprint=fp).count() == 2


@pytest.mark.django_db
def test_execution_finish_dispatches_training_and_drift_notifications(django_capture_on_commit_callbacks):
    from apps.drift.models import DriftMonitor, DriftRun
    from apps.observability.execution.observations import _finish
    from apps.registry.models import ModelVersion
    from apps.training.tests.factories import training_job

    user = get_user_model().objects.create_user("exec-notify@example.com", "pass123")
    project = ModelProject.objects.create(owner=user, name="NotifyModel")
    version = ModelVersion.objects.create(project=project, version="1")
    job = training_job(project=project, status="running", backend="docker")
    monitor = DriftMonitor.objects.create(
        version=version,
        reference_uri="s3://bucket/ref.csv",
        is_active=True,
    )
    drift_run = DriftRun.objects.create(
        monitor=monitor,
        status="running",
        has_drift=True,
        drift_score=0.42,
    )

    with (
        patch("apps.notifications.events.notify_training_result") as mock_train,
        patch("apps.notifications.events.notify_drift_result") as mock_drift,
        django_capture_on_commit_callbacks(execute=True),
    ):
        _finish(job, "training", "failed", message="OOMKilled")
        _finish(drift_run, "drift", "completed")

    assert mock_train.call_count == 1
    assert mock_train.call_args[0][0].pk == job.pk
    assert mock_drift.call_count == 1
    assert mock_drift.call_args[0][0].pk == drift_run.pk
