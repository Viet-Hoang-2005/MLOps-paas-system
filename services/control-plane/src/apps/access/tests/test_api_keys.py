import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject


@pytest.mark.django_db
def test_api_key_can_only_scope_projects_owned_by_user():
    owner = get_user_model().objects.create_user("owner@example.com", "password123")
    stranger = get_user_model().objects.create_user("stranger@example.com", "password123")
    foreign_project = ModelProject.objects.create(owner=stranger, name="foreign")
    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(
        "/api/api-keys/",
        {
            "name": "invalid",
            "allowed_projects": [str(foreign_project.public_id)],
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_api_key_secret_is_returned_only_when_created():
    user = get_user_model().objects.create_user("owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="project")
    client = APIClient()
    client.force_authenticate(user)

    created = client.post(
        "/api/api-keys/",
        {"name": "client", "allowed_projects": [str(project.public_id)]},
        format="json",
    )
    listed = client.get("/api/api-keys/")

    assert created.status_code == 201
    assert created.data["key"].startswith("mlp_")
    assert "key" not in listed.data["results"][0]
