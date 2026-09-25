import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject


@pytest.mark.django_db
def test_manual_build_and_build_upload_routes_are_read_only_or_removed():
    owner = get_user_model().objects.create_user("manual-build-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Draft only build source")
    client = APIClient()
    client.force_authenticate(owner)

    assert client.post(f"/api/models/{project.public_id}/builds/", {}, format="json").status_code == 405
    assert client.post(f"/api/models/{project.public_id}/builds/upload-url/", {}, format="json").status_code == 404
    assert client.post("/api/builds/", {}, format="json").status_code == 405
