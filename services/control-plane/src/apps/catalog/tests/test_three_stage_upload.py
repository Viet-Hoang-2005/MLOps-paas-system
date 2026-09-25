import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject


@pytest.mark.django_db
def test_project_metadata_patch_preserves_omitted_fields_and_manual_build_is_removed():
    owner = get_user_model().objects.create_user("workflow-owner@example.com", "password123")
    project = ModelProject.objects.create(
        owner=owner,
        name="Workflow project",
        task_domain="multiclass_classification",
    )
    client = APIClient()
    client.force_authenticate(owner)

    response = client.patch(
        f"/api/models/{project.public_id}/",
        {"name": "Renamed project"},
        format="json",
    )

    assert response.status_code == 200
    project.refresh_from_db()
    assert project.name == "Renamed project"
    assert project.task_domain == "multiclass_classification"
    assert client.post(f"/api/models/{project.public_id}/builds/", {}, format="json").status_code == 405
