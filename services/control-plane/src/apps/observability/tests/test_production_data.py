import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.observability import selectors
from apps.production.models import PredictionRecord


@pytest.mark.django_db
def test_latest_production_data_returns_stable_frontend_fields():
    owner = get_user_model().objects.create_user("prediction-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Prediction model")
    version = project.versions.create(version="1")
    PredictionRecord.objects.create(
        project=project,
        model_version=version,
        observed_at="2026-01-01T00:00:00Z",
        features={"feature": 1},
        prediction="safe",
    )

    results = selectors.latest_production_data(project, limit=1)

    assert list(results[0]) == ["id", "project_id", "model_version_id", "timestamp", "features", "prediction"]
    assert results[0]["features"] == {"feature": 1}
    assert results[0]["project_id"] == str(project.public_id)


@pytest.mark.django_db
def test_production_data_endpoint_requires_project_owner_and_validates_limit(monkeypatch):
    owner = get_user_model().objects.create_user("production-owner@example.com", "password123")
    stranger = get_user_model().objects.create_user("production-stranger@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Production model")
    captured = []

    def fake_latest_production_data(selected_project, limit=100, version_id=None):
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
    assert captured[-1] == (project, 100)


@pytest.mark.django_db
def test_production_preview_returns_at_most_available_rows_and_scopes_version():
    owner = get_user_model().objects.create_user("preview-production@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Production preview")
    first = project.versions.create(version="1")
    second = project.versions.create(version="2")
    other_project = ModelProject.objects.create(owner=owner, name="Other project")
    foreign = other_project.versions.create(version="1")
    for version, count in ((first, 3), (second, 2), (foreign, 1)):
        for index in range(count):
            PredictionRecord.objects.create(
                project=version.project, model_version=version, observed_at=f"2026-01-01T00:00:0{index}Z",
                features={"x": index}, prediction=str(index),
            )
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/models/{project.public_id}/production-data/"
    assert len(client.get(f"{url}?limit=100").data) == 5
    response = client.get(f"{url}?limit=100&version_id={first.public_id}")
    assert len(response.data) == 3
    assert all(item["model_version_id"] == str(first.public_id) for item in response.data)
    assert [item["features"]["x"] for item in response.data] == [2, 1, 0]
    assert len(client.get(f"{url}?limit=1&version_id={first.public_id}").data) == 1
    assert client.get(f"{url}?version_id={foreign.public_id}").status_code == 404
    assert client.get(f"{url}?version_id=invalid").status_code == 400
    assert client.get(f"{url}?limit=10001").status_code == 400


@pytest.mark.django_db
def test_production_preview_empty_version_returns_empty_list():
    owner = get_user_model().objects.create_user("empty-production@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Empty project")
    version = project.versions.create(version="1")
    client = APIClient()
    client.force_authenticate(owner)
    assert client.get(f"/api/models/{project.public_id}/production-data/?limit=100&version_id={version.public_id}").data == []
