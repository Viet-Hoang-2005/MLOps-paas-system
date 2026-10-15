import uuid
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.notifications.models import Notification
from apps.notifications.services import (
    create_notification,
    delete_notification,
    mark_all_notifications_as_read,
    mark_notification_as_read,
)


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
