from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.observability import selectors


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.execute = Mock()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def fetchall(self):
        return self.rows


def test_latest_production_data_scopes_query_and_applies_optional_limit():
    project = Mock(public_id="project-uuid", owner=Mock(tenant_id="tenant-uuid"))
    cursor = Cursor(
        [
            (
                "event-1",
                "project-uuid",
                "version-uuid",
                None,
                '{"feature": 1}',
                "safe",
            )
        ]
    )
    connection = Mock(vendor="postgresql")
    connection.introspection.table_names.return_value = ["paas_production_logs"]
    connection.cursor.return_value = cursor

    results = selectors.latest_production_data(project, limit=100, db_connection=connection)

    assert results[0]["features"] == {"feature": 1}
    sql, params = cursor.execute.call_args.args
    assert 'FROM "public"."paas_production_logs"' in sql
    assert "LIMIT %s" in sql
    assert params == ["tenant-uuid", "project-uuid", 100]

    selectors.latest_production_data(project, db_connection=connection)
    sql, params = cursor.execute.call_args.args
    assert "LIMIT %s" not in sql
    assert params == ["tenant-uuid", "project-uuid"]


def test_latest_production_data_returns_empty_when_consumer_table_is_missing():
    project = Mock(public_id="project-uuid", owner=Mock(tenant_id="tenant-uuid"))
    connection = Mock(vendor="postgresql")
    connection.introspection.table_names.return_value = []

    assert selectors.latest_production_data(project, db_connection=connection) == []
    connection.cursor.assert_not_called()


@pytest.mark.django_db
def test_production_data_endpoint_requires_project_owner_and_validates_limit(monkeypatch):
    owner = get_user_model().objects.create_user("production-owner@example.com", "password123")  # type: ignore[attr-defined]
    stranger = get_user_model().objects.create_user("production-stranger@example.com", "password123")  # type: ignore[attr-defined]
    project = ModelProject.objects.create(owner=owner, name="Production model")
    captured = []

    def fake_latest_production_data(selected_project, limit=None):
        captured.append((selected_project, limit))
        return [{"id": "event-1", "features": {"feature": 1}, "prediction": "safe"}]

    monkeypatch.setattr(
        "apps.observability.api.endpoints.latest_production_data",
        fake_latest_production_data,
    )
    url = f"/api/models/{project.public_id}/production-data/"
    client = APIClient()

    assert client.get(url).status_code == 401

    client.force_authenticate(stranger)
    assert client.get(url).status_code == 404
    assert captured == []

    client.force_authenticate(owner)
    response = client.get(f"{url}?limit=100")
    assert response.status_code == 200
    assert response.data[0]["id"] == "event-1"
    assert captured == [(project, 100)]

    assert client.get(f"{url}?limit=0").status_code == 400
    assert client.get(f"{url}?limit=not-a-number").status_code == 400

    response = client.get(url)
    assert response.status_code == 200
    assert captured[-1] == (project, None)
