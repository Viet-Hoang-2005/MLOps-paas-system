"""Explicit PostgreSQL regression suite; SQLite cannot exercise FOR UPDATE joins."""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build
from apps.registry.models import ModelVersion


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("initial_status", "deletion_state", "incoming", "registered", "expected_status", "duplicate"),
    [
        ("building", "active", "success", False, "ready", False),
        ("building", "active", "failed", False, "failed", False),
        ("ready", "active", "error", False, "ready", True),
        ("ready", "active", "success", True, "ready", True),
        ("building", "deleting", "success", False, "cancelled", False),
    ],
)
@override_settings(CONTROL_PLANE_WEBHOOK_SECRET="integration-webhook-secret")
def test_build_callback_locks_only_build_with_nullable_version(
    monkeypatch, initial_status, deletion_state, incoming, registered, expected_status, duplicate
):
    assert connection.vendor == "postgresql", "Run with --ds=config.settings.test_postgres, not SQLite."
    owner = get_user_model().objects.create_user("callback@example.com", "test-password")
    project = ModelProject.objects.create(owner=owner, name="callback regression")
    version = ModelVersion.objects.create(project=project, version="1") if registered else None
    build = Build.objects.create(
        project=project, version=version, flavor="sklearn", status=initial_status, deletion_state=deletion_state
    )
    cleanup = []
    deletion = []
    monkeypatch.setattr(
        "apps.deployment.api.webhooks.cleanup_failed_build_artifacts.delay",
        lambda *args: cleanup.append(args),
    )
    monkeypatch.setattr("apps.deployment.api.webhooks.delete_build.delay", lambda *args: deletion.append(args))
    client = APIClient()

    with CaptureQueriesContext(connection) as queries:
        response = client.post(
            f"/internal/webhooks/builds/{build.public_id}/",
            {"status": incoming, "image_digest": "sha256:" + "a" * 64},
            format="json",
            HTTP_X_CONTROL_PLANE_SECRET="integration-webhook-secret",
        )

    assert response.status_code == 200
    build.refresh_from_db()
    assert build.status == expected_status
    assert build.version_id == (version.pk if version else None)
    assert build.execution_completed_at is not None
    assert response.data.get("duplicate", False) is duplicate
    assert response.data["version_id"] == (str(version.public_id) if version else None)
    assert len(cleanup) == int(expected_status == "failed" and not duplicate)
    assert len(deletion) == int(deletion_state == "deleting")

    # Exercise the real join and SQL lock scope, rather than mock the ORM away.
    joined_locks = [
        query["sql"]
        for query in queries.captured_queries
        if 'LEFT OUTER JOIN "registry_modelversion"' in query["sql"] and "FOR UPDATE" in query["sql"]
    ]
    assert len(joined_locks) == 1
    assert joined_locks[0].endswith('FOR UPDATE OF "deployment_build"')
