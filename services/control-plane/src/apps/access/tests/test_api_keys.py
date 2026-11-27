import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject


@pytest.mark.django_db
def test_api_key_regenerate_returns_404_for_missing_or_revoked_key():
    User = get_user_model()
    owner = User.objects.create_user("key-owner@example.com", "password123")
    other = User.objects.create_user("key-other@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="KeyProject")

    client = APIClient()
    client.force_authenticate(owner)

    # Missing key returns 404 (not 500)
    assert client.post(f"/api/api-keys/{uuid.uuid4()}/regenerate/").status_code == 404

    created = client.post(
        "/api/api-keys/",
        {"name": "ci-key", "allowed_projects": [str(project.public_id)]},
        format="json",
    )
    assert created.status_code == 201
    key_id = created.data["id"]

    # Another user cannot regenerate
    client.force_authenticate(other)
    assert client.post(f"/api/api-keys/{key_id}/regenerate/").status_code == 404

    # Revoking the key makes regenerate return 404
    client.force_authenticate(owner)
    assert client.delete(f"/api/api-keys/{key_id}/").status_code == 204
    assert client.post(f"/api/api-keys/{key_id}/regenerate/").status_code == 404


@pytest.mark.django_db
def test_api_key_name_conflict_allows_reuse_after_revoke():
    User = get_user_model()
    owner = User.objects.create_user("key-name@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="KeyNameProject")

    client = APIClient()
    client.force_authenticate(owner)

    first = client.post(
        "/api/api-keys/",
        {"name": "deploy-key", "allowed_projects": [str(project.public_id)]},
        format="json",
    )
    assert first.status_code == 201

    # Duplicate active name returns 409 (not 500)
    dup = client.post(
        "/api/api-keys/",
        {"name": "deploy-key", "allowed_projects": [str(project.public_id)]},
        format="json",
    )
    assert dup.status_code == 409

    # After revoking, creating a new key with the same name succeeds
    assert client.delete(f"/api/api-keys/{first.data['id']}/").status_code == 204
    reused = client.post(
        "/api/api-keys/",
        {"name": "deploy-key", "allowed_projects": [str(project.public_id)]},
        format="json",
    )
    assert reused.status_code == 201
