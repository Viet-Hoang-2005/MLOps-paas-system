import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.catalog.services.draft import ensure_project_draft


@pytest.fixture
def tenant_a(db):
    return get_user_model().objects.create_user("tenant-a@example.com", "password123")


@pytest.fixture
def tenant_b(db):
    return get_user_model().objects.create_user("tenant-b@example.com", "password123")


@pytest.fixture
def project_tenant_a(tenant_a):
    return ModelProject.objects.create(
        owner=tenant_a,
        name="Confidential Medical Model",
        description="Tenant A private AI project",
        task_domain="binary_classification",
        access_mode="private",
    )


@pytest.mark.django_db
def test_tenant_storage_isolation(project_tenant_a, tenant_b):
    ensure_project_draft(project=project_tenant_a)

    client = APIClient()
    client.force_authenticate(tenant_b)

    # 1. Tenant B không thể xem Overview của Tenant A (404 Not Found)
    res_overview = client.get(f"/api/models/{project_tenant_a.public_id}/overview/")
    assert res_overview.status_code == 404

    # 2. Tenant B không thể xem không gian Draft của Tenant A (404 Not Found)
    res_draft = client.get(f"/api/models/{project_tenant_a.public_id}/draft/")
    assert res_draft.status_code == 404

    # 3. Tenant B không thể xin Presigned URL upload vào Draft của Tenant A
    res_upload = client.post(
        f"/api/models/{project_tenant_a.public_id}/draft/assets/upload-url/",
        {"kind": "model", "filename": "trojan.joblib", "size_bytes": 1024},
        format="json",
    )
    assert res_upload.status_code == 404

    # 4. Tenant B không thể gửi yêu cầu lưu draft của Tenant A
    res_save = client.post(
        f"/api/models/{project_tenant_a.public_id}/draft/save/",
        {"expected_revision": 1},
        format="json",
    )
    assert res_save.status_code == 404
