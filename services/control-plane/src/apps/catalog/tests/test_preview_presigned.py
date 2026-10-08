import hashlib
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
    monkeypatch.setattr(
        "apps.catalog.api.endpoints.generate_preview_upload_urls",
        lambda **kwargs: __import__(
            "apps.catalog.services.preview", fromlist=["generate_preview_upload_urls"]
        ).generate_preview_upload_urls(**kwargs, storage=storage),
    )

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
    # Presigned URLs MUST target ephemeral staging area with staging/ prefix for S3 lifecycle cleanup
    assert f"staging/{project_prefix(owner.tenant_id, project.public_id)}/preview/" in artifact_item["s3_uri"]
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
    monkeypatch.setattr(
        "apps.catalog.api.endpoints.generate_preview_upload_urls",
        lambda **kwargs: __import__(
            "apps.catalog.services.preview", fromlist=["generate_preview_upload_urls"]
        ).generate_preview_upload_urls(**kwargs, storage=storage),
    )

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
    assert "staging/" in data["files"][0]["s3_uri"]

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
def test_presigned_preview_update_promotes_to_committed_and_prevents_overwrite(project, owner, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.catalog.api.serializers.S3Storage", lambda: storage)

    # 1. Client uploads initial file to staging key via presigned PUT
    prefix = project_prefix(owner.tenant_id, project.public_id)
    staging_key = f"staging/{prefix}/preview/batch-1/source_artifact/model.pkl"
    stored_staging = storage.put(
        staging_key, SimpleUploadedFile("model.pkl", b"original-valid-model"), "application/octet-stream"
    )

    client = APIClient()
    client.force_authenticate(owner)

    # 2. Client saves preview
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
                    "s3_uri": stored_staging.uri,
                }
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    project.refresh_from_db()
    assert project.preview.revision == 2
    assert project.preview.assets.count() == 1

    asset = project.preview.assets.first()
    assert asset.kind == "source_artifact"
    # P1 Integrity Check 1: Asset URI is promoted to committed path, NOT the staging key
    assert asset.s3_uri != stored_staging.uri
    assert "/preview/committed/" in asset.s3_uri
    assert asset.size_bytes == len(b"original-valid-model")
    # Checksum MUST be SHA-256 hex string (64 chars), not MD5 ETag
    import hashlib
    assert asset.checksum == hashlib.sha256(b"original-valid-model").hexdigest()

    # P1 Integrity Check 2: Staging object is deleted upon commit
    assert stored_staging.uri not in storage.objects

    # P1 Integrity Check 3: Simulating attacker re-using the still-active presigned PUT URL
    # Attacker uploads malicious bytes to the original staging URL
    storage.put(staging_key, SimpleUploadedFile("model.pkl", b"MALICIOUS_OVERWRITE_DATA"), "application/octet-stream")

    # Verify: PreviewAsset is 100% immune; reading asset.s3_uri still yields original bytes!
    assert storage.read(asset.s3_uri) == b"original-valid-model"


@pytest.mark.django_db
def test_presigned_create_project_with_preallocated_id(owner, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.catalog.api.serializers.S3Storage", lambda: storage)

    project_id = uuid.uuid4()
    prefix = project_prefix(owner.tenant_id, project_id)
    staging_key = f"staging/{prefix}/preview/batch-new/source_artifact/model.joblib"
    stored_staging = storage.put(
        staging_key, SimpleUploadedFile("model.joblib", b"trained-joblib-content"), "application/octet-stream"
    )

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
                    "s3_uri": stored_staging.uri,
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
    asset = project.preview.assets.first()
    assert "/preview/committed/" in asset.s3_uri
    assert storage.read(asset.s3_uri) == b"trained-joblib-content"
    assert asset.checksum == hashlib.sha256(b"trained-joblib-content").hexdigest()
    # Staging was deleted
    assert stored_staging.uri not in storage.objects


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
    malicious_uri = f"s3://{storage.bucket}/staging/users/other-tenant/models/{uuid.uuid4()}/preview/x/source_artifact/model.pkl"
    res1 = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "assets": [{"kind": "source_artifact", "name": "model.pkl", "s3_uri": malicious_uri}],
        },
        format="json",
    )
    assert res1.status_code == 400
    assert "does not belong to this project's preview staging area" in str(res1.data)

    # 2. Attempt to reference an object outside staging (e.g. attempting to pass committed path)
    prefix = project_prefix(owner.tenant_id, project.public_id)
    direct_committed_uri = f"s3://{storage.bucket}/{prefix}/preview/committed/b1/source_artifact/model.pkl"
    res2 = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "assets": [{"kind": "source_artifact", "name": "model.pkl", "s3_uri": direct_committed_uri}],
        },
        format="json",
    )
    assert res2.status_code == 400
    assert "does not belong to this project's preview staging area" in str(res2.data)

    # 3. Attempt to reference an object that does not exist in S3 staging
    nonexistent_uri = f"s3://{storage.bucket}/staging/{prefix}/preview/b1/source_artifact/missing.pkl"
    res3 = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "assets": [{"kind": "source_artifact", "name": "missing.pkl", "s3_uri": nonexistent_uri}],
        },
        format="json",
    )
    assert res3.status_code == 400
    assert "Could not verify uploaded asset" in str(res3.data)

    # 4. Attempt to reference an empty object in S3 staging
    empty_key = f"staging/{prefix}/preview/b1/source_artifact/empty.pkl"
    stored_empty = storage.put(empty_key, SimpleUploadedFile("empty.pkl", b""), "application/octet-stream")
    res4 = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "assets": [{"kind": "source_artifact", "name": "empty.pkl", "s3_uri": stored_empty.uri}],
        },
        format="json",
    )
    assert res4.status_code == 400
    assert "is empty" in str(res4.data)
    # Failed saves keep staging until its lifecycle expiry or a successful retry.
    assert stored_empty.uri in storage.objects


@pytest.mark.django_db
def test_generate_upload_urls_with_mlflow_zip_format(owner, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr(
        "apps.catalog.api.endpoints.generate_preview_upload_urls",
        lambda **kwargs: __import__(
            "apps.catalog.services.preview", fromlist=["generate_preview_upload_urls"]
        ).generate_preview_upload_urls(**kwargs, storage=storage),
    )

    client = APIClient()
    client.force_authenticate(owner)

    # 1. Request URL with artifact_format="mlflow_zip" and model.zip -> SUCCESS
    res_zip = client.post(
        "/api/models/preview/upload-urls/",
        {
            "name": "MLflow Model",
            "flavor": "sklearn",
            "artifact_format": "mlflow_zip",
            "files": [{"kind": "source_artifact", "filename": "model.zip"}],
        },
        format="json",
    )
    assert res_zip.status_code == 200, res_zip.data

    # 2. Request URL with artifact_format="mlflow_zip" but non-zip filename -> 400 Validation Error
    res_bad = client.post(
        "/api/models/preview/upload-urls/",
        {
            "name": "MLflow Bad Model",
            "flavor": "sklearn",
            "artifact_format": "mlflow_zip",
            "files": [{"kind": "source_artifact", "filename": "model.pkl"}],
        },
        format="json",
    )
    assert res_bad.status_code == 400
    assert "A model package upload requires a .zip file." in str(res_bad.data)


@pytest.mark.django_db
def test_generate_upload_urls_for_existing_project_with_new_flavor(project, owner, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr(
        "apps.catalog.api.endpoints.generate_preview_upload_urls",
        lambda **kwargs: __import__(
            "apps.catalog.services.preview", fromlist=["generate_preview_upload_urls"]
        ).generate_preview_upload_urls(**kwargs, storage=storage),
    )

    # Project currently has flavor="sklearn"
    project.preview.flavor = "sklearn"
    project.preview.save(update_fields=["flavor"])

    client = APIClient()
    client.force_authenticate(owner)

    # User in UI changes flavor to "pytorch" and uploads a ".pt" file
    res = client.post(
        f"/api/models/{project.public_id}/preview/upload-urls/",
        {
            "flavor": "pytorch",
            "artifact_format": "raw",
            "files": [{"kind": "source_artifact", "filename": "model.pt"}],
        },
        format="json",
    )
    # Must succeed because flavor is evaluated as "pytorch", not the old "sklearn"
    assert res.status_code == 200, res.data


@pytest.mark.django_db
def test_save_preview_validates_existing_retained_artifact_on_flavor_or_format_change(project, owner, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.catalog.api.serializers.S3Storage", lambda: storage)

    # Project starts with flavor="sklearn" and existing asset model.pkl
    project.preview.flavor = "sklearn"
    project.preview.artifact_format = "raw"
    project.preview.save(update_fields=["flavor", "artifact_format"])

    prefix = project_prefix(owner.tenant_id, project.public_id)
    committed_key = f"{prefix}/preview/committed/c1/source_artifact/model.pkl"
    stored_committed = storage.put(committed_key, SimpleUploadedFile("model.pkl", b"valid-pkl"), "application/octet-stream")
    project.preview.assets.create(
        kind="source_artifact",
        name="model.pkl",
        s3_uri=stored_committed.uri,
        size_bytes=len(b"valid-pkl"),
    )

    # Put a metrics file in staging
    staging_metrics_key_1 = f"staging/{prefix}/preview/b2/metrics/metrics.json"
    stored_metrics_1 = storage.put(staging_metrics_key_1, SimpleUploadedFile("metrics.json", b'{"acc": 0.9}'), "application/json")

    client = APIClient()
    client.force_authenticate(owner)

    # 1. User changes flavor to "pytorch" without re-uploading artifact (model.pkl is incompatible with pytorch)
    res_bad_flavor = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "flavor": "pytorch",
            "assets": [{"kind": "metrics", "name": "metrics.json", "s3_uri": stored_metrics_1.uri}],
        },
        format="json",
    )
    assert res_bad_flavor.status_code == 400
    assert "Pytorch raw models require one of: .pt, .pth" in str(res_bad_flavor.data)
    assert stored_metrics_1.uri in storage.objects

    # 2. User changes artifact_format to "mlflow_zip" without re-uploading artifact (model.pkl is not a .zip)
    staging_metrics_key_2 = f"staging/{prefix}/preview/b3/metrics/metrics.json"
    stored_metrics_2 = storage.put(staging_metrics_key_2, SimpleUploadedFile("metrics.json", b'{"acc": 0.9}'), "application/json")
    res_bad_format = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "flavor": "sklearn",
            "artifact_format": "mlflow_zip",
            "assets": [{"kind": "metrics", "name": "metrics.json", "s3_uri": stored_metrics_2.uri}],
        },
        format="json",
    )
    assert res_bad_format.status_code == 400
    assert "A model package upload requires a .zip file." in str(res_bad_format.data)
    assert stored_metrics_2.uri in storage.objects

    # 3. User changes flavor to "xgboost" (which accepts .pkl) -> SUCCESS
    staging_metrics_key_3 = f"staging/{prefix}/preview/b4/metrics/metrics.json"
    stored_metrics_3 = storage.put(staging_metrics_key_3, SimpleUploadedFile("metrics.json", b'{"acc": 0.9}'), "application/json")
    res_ok = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": project.preview.revision,
            "flavor": "xgboost",
            "assets": [{"kind": "metrics", "name": "metrics.json", "s3_uri": stored_metrics_3.uri}],
        },
        format="json",
    )
    assert res_ok.status_code == 200, res_ok.data
    project.refresh_from_db()
    assert project.preview.flavor == "xgboost"
    assert project.preview.assets.count() == 2


@pytest.mark.django_db
def test_save_preview_keeps_staging_objects_on_failure(project, owner, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.catalog.api.serializers.S3Storage", lambda: storage)

    prefix = project_prefix(owner.tenant_id, project.public_id)
    staging_key = f"staging/{prefix}/preview/b-fail/source_artifact/model.pkl"
    stored_staging = storage.put(
        staging_key, SimpleUploadedFile("model.pkl", b"valid-bytes"), "application/octet-stream"
    )

    client = APIClient()
    client.force_authenticate(owner)

    # Attempt to save preview with conflicting revision (revision mismatch)
    response = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {
            "revision": 9999,  # Mismatch triggers Conflict
            "flavor": "sklearn",
            "assets": [{"kind": "source_artifact", "name": "model.pkl", "s3_uri": stored_staging.uri}],
        },
        format="json",
    )
    assert response.status_code == 409
    assert stored_staging.uri in storage.objects

