import pytest
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalog.models import DraftAsset, ModelProject
from apps.catalog.services.draft import ensure_project_draft, save_draft


class FakeStorage:
    bucket = "test-bucket"

    def copy(self, _source, key):
        return SimpleNamespace(uri=f"s3://test-bucket/{key}", checksum="sha256", size_bytes=100, content_type="application/octet-stream")

    def delete_prefix(self, _prefix):
        pass

    def presigned_get(self, uri, _expires_in=900):
        return uri


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("be-draft-owner@example.com", "password123")


@pytest.fixture
def project(owner):
    return ModelProject.objects.create(
        owner=owner,
        name="Credit Scoring Project",
        description="Draft workspace test project",
        task_domain="binary_classification",
    )


@pytest.mark.django_db
def test_save_draft_missing_mandatory_assets(project, owner):
    draft = ensure_project_draft(project=project)

    # 1. Trực tiếp service level
    with pytest.raises(ValidationError) as exc:
        save_draft(draft=draft, expected_revision=draft.revision)
    assert "mandatory assets" in str(exc.value).lower()

    # 2. Qua REST API endpoint
    client = APIClient()
    client.force_authenticate(owner)
    res = client.post(
        f"/api/models/{project.public_id}/draft/save/",
        {"expected_revision": draft.revision},
        format="json",
    )
    assert res.status_code == 400
    assert "mandatory assets" in str(res.data).lower()


@pytest.mark.django_db
def test_save_draft_optional_code_allowed(project, owner, monkeypatch):
    draft = ensure_project_draft(project=project)

    DraftAsset.objects.create(
        draft=draft,
        kind="model",
        name="model.joblib",
        s3_uri="s3://test-bucket/models/model.joblib",
        checksum="sha256:model123",
        size_bytes=1024,
    )
    DraftAsset.objects.create(
        draft=draft,
        kind="reference_data",
        name="reference.parquet",
        s3_uri="s3://test-bucket/data/reference.parquet",
        checksum="sha256:ref123",
        size_bytes=2048,
    )

    monkeypatch.setattr("apps.catalog.services.draft.S3Storage", FakeStorage)
    monkeypatch.setattr("infrastructure.storage.S3Storage", FakeStorage)
    client = APIClient()
    client.force_authenticate(owner)
    res = client.post(
        f"/api/models/{project.public_id}/draft/save/",
        {"expected_revision": draft.revision},
        format="json",
    )
    assert res.status_code == 200
    draft.refresh_from_db()
    assert draft.status == "ready"
    assert draft.saved_revision == draft.revision


@pytest.mark.django_db
def test_draft_optimistic_concurrency_conflict(project, owner):
    draft = ensure_project_draft(project=project)
    draft.revision = 2
    draft.save(update_fields=["revision"])

    client = APIClient()
    client.force_authenticate(owner)
    res = client.post(
        f"/api/models/{project.public_id}/draft/save/",
        {"expected_revision": 1},
        format="json",
    )
    assert res.status_code == 409
    assert res.data["error"]["code"] == "conflict"
    assert "revision" in str(res.data["error"]["detail"]).lower()
