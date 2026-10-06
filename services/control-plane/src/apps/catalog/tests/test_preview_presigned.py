import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from infrastructure.storage.paths import project_prefix


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("owner@example.test", "test-password")


@pytest.fixture
def stranger(db):
    return get_user_model().objects.create_user("stranger@example.test", "test-password")


@pytest.fixture
def project(db, owner):
    return ModelProject.objects.create(owner=owner, name="Presigned Test Project")


@pytest.mark.django_db
def test_generate_preview_upload_urls_for_existing_project(project, owner, stranger, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.catalog.api.endpoints.generate_preview_upload_urls", lambda **kwargs: __import__("apps.catalog.services.preview", fromlist=["generate_preview_upload_urls"]).generate_preview_upload_urls(**kwargs, storage=storage))

    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(
        f"/api/models/{project.public_id}/preview/upload-urls/",
        {
            "files": [
                {
                    "kind": "source_artifact",
                    "filename": "model.joblib",
                    "size_bytes": 1024,
                    "content_type": "application/octet-stream",
                },
                {
                    "kind": "source_code",
                    "filename": "serve.py",
                    "size_bytes": 2048,
                    "content_type": "text/x-python",
                },
            ]
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    data = response.data
    assert data["project_id"] == str(project.public_id)
    assert len(data["files"]) == 2

    artifact_item = next(f for f in data["files"] if f["kind"] == "source_artifact")
    assert artifact_item["filename"] == "model.joblib"
    assert f"{project_prefix(owner.tenant_id, project.public_id)}/preview/" in artifact_item["s3_uri"]
    assert artifact_item["upload_url"].startswith(f"https://{storage.bucket}.s3.test/")

    # Stranger should receive 404
    client.force_authenticate(stranger)
    res_stranger = client.post(
        f"/api/models/{project.public_id}/preview/upload-urls/",
        {"files": [{"kind": "source_artifact", "filename": "model.joblib"}]},
        format="json",
    )
    assert res_stranger.status_code == 404


@pytest.mark.django_db
def test_generate_preview_upload_urls_for_new_project(owner, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.catalog.api.endpoints.generate_preview_upload_urls", lambda **kwargs: __import__("apps.catalog.services.preview", fromlist=["generate_preview_upload_urls"]).generate_preview_upload_urls(**kwargs, storage=storage))

    client = APIClient()
    client.force_authenticate(owner)

    # 1. Successful pre-allocation
    response = client.post(
        "/api/models/preview/upload-urls/",
        {
            "name": "New Preallocated Model",
            "flavor": "sklearn",
            "files": [
                {
                    "kind": "source_artifact",
                    "filename": "model.pkl",
                    "size_bytes": 5000,
                }
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    data = response.data
    allocated_id = uuid.UUID(data["project_id"])
    assert len(data["files"]) == 1
    assert str(allocated_id) in data["files"][0]["s3_uri"]

    # 2. Duplicate name validation returns 409 Conflict
    ModelProject.objects.create(owner=owner, name="Existing Name")
    dup_res = client.post(
        "/api/models/preview/upload-urls/",
        {
            "name": "Existing Name",
            "flavor": "sklearn",
            "files": [{"kind": "source_artifact", "filename": "model.pkl"}],
        },
        format="json",
    )
    assert dup_res.status_code == 409


@pytest.mark.django_db
def test_presigned_preview_update_fast_path(project, owner, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.catalog.api.serializers.S3Storage", lambda: storage)

    # Upload mock artifact directly to S3
    prefix = project_prefix(owner.tenant_id, project.public_id)
    s3_key = f"{prefix}/preview/batch-1/source_artifact/model.pkl"
    stored = storage.put(s3_key, SimpleUploadedFile("model.pkl", b"model-bytes-content"), "application/octet-stream")

    client = APIClient()
    client.force_authenticate(owner)

    response = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "flavor": "sklearn",
            "requirements_text": "scikit-learn==1.4.0",
            "assets": [
                {
                    "kind": "source_artifact",
                    "name": "model.pkl",
                    "s3_uri": stored.uri,
                }
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    project.refresh_from_db()
    assert project.preview.revision == 2
    assert project.preview.requirements_text == "scikit-learn==1.4.0"
    assert project.preview.assets.count() == 1
    asset = project.preview.assets.first()
    assert asset.kind == "source_artifact"
    assert asset.s3_uri == stored.uri
    assert asset.size_bytes == len(b"model-bytes-content")


@pytest.mark.django_db
def test_presigned_create_project_with_preallocated_id(owner, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.catalog.api.serializers.S3Storage", lambda: storage)

    project_id = uuid.uuid4()
    prefix = project_prefix(owner.tenant_id, project_id)
    s3_key = f"{prefix}/preview/batch-new/source_artifact/model.joblib"
    stored = storage.put(s3_key, SimpleUploadedFile("model.joblib", b"trained-joblib-content"), "application/octet-stream")

    client = APIClient()
    client.force_authenticate(owner)

    response = client.post(
        "/api/models/",
        {
            "project_id": str(project_id),
            "name": "Created Via Presigned S3",
            "description": "Fast upload project",
            "access_mode": "private",
            "flavor": "sklearn",
            "assets": [
                {
                    "kind": "source_artifact",
                    "name": "model.joblib",
                    "s3_uri": stored.uri,
                }
            ],
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    created_id = response.data["id"]
    assert created_id == str(project_id)

    project = ModelProject.objects.get(public_id=project_id)
    assert project.name == "Created Via Presigned S3"
    assert project.preview.assets.count() == 1
    assert project.preview.assets.first().s3_uri == stored.uri


@pytest.mark.django_db
def test_presigned_security_confinement_and_validation(project, owner, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.catalog.api.serializers.S3Storage", lambda: storage)

    project.preview.flavor = "sklearn"
    project.preview.save(update_fields=["flavor"])

    client = APIClient()
    client.force_authenticate(owner)

    # 1. Attempt to use S3 URI belonging to another project/tenant
    malicious_uri = f"s3://{storage.bucket}/users/other-tenant/models/{uuid.uuid4()}/preview/x/source_artifact/model.pkl"
    res1 = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "assets": [{"kind": "source_artifact", "name": "model.pkl", "s3_uri": malicious_uri}],
        },
        format="json",
    )
    assert res1.status_code == 400
    assert "does not belong to this project preview" in str(res1.data)

    # 2. Attempt to reference an object that does not exist in S3
    prefix = project_prefix(owner.tenant_id, project.public_id)
    nonexistent_uri = (
        f"s3://{storage.bucket}/{prefix}/preview/b1/source_artifact/missing.pkl"
    )
    res2 = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "assets": [{"kind": "source_artifact", "name": "missing.pkl", "s3_uri": nonexistent_uri}],
        },
        format="json",
    )
    assert res2.status_code == 400
    assert "Could not verify uploaded asset" in str(res2.data)

    # 3. Attempt to reference an empty object in S3
    empty_key = f"{prefix}/preview/b1/source_artifact/empty.pkl"
    stored_empty = storage.put(empty_key, SimpleUploadedFile("empty.pkl", b""), "application/octet-stream")
    res3 = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "assets": [{"kind": "source_artifact", "name": "empty.pkl", "s3_uri": stored_empty.uri}],
        },
        format="json",
    )
    assert res3.status_code == 400
    assert "is empty" in str(res3.data)
