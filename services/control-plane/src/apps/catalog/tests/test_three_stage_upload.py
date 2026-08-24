from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from infrastructure.storage.s3 import StoredObject
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, BuildInputAsset


class FakeStorage:
    def __init__(self):
        self.deleted = []

    def put(self, key, body, content_type):
        payload = body.read()
        return StoredObject(key, f"s3://test-bucket/{key}", "checksum", len(payload), content_type)

    def delete(self, uri):
        self.deleted.append(uri)

    def delete_prefix(self, prefix):
        self.deleted.append(prefix)


@pytest.mark.django_db
def test_metadata_is_latest_only_and_assets_are_tenant_scoped(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr("apps.catalog.services.project_metadata.S3Storage", lambda: storage)
    owner = get_user_model().objects.create_user("metadata-owner@example.com", "password123")
    other = get_user_model().objects.create_user("metadata-other@example.com", "password123")
    client = APIClient()
    client.force_authenticate(owner)
    created = client.post(
        "/api/models/",
        {
            "name": "NIDS",
            "description": "Network detector",
            "access_mode": "private",
            "source_code_file": SimpleUploadedFile("source.py", b"print('ok')", "text/x-python"),
            "reference_data_file": SimpleUploadedFile("reference.csv", b"x\n1", "text/csv"),
        },
        format="multipart",
    )
    assert created.status_code == 201
    assert created.data["source_code"]["name"] == "source.py"
    assert created.data["reference_data"]["name"] == "reference.csv"
    project = ModelProject.objects.get(public_id=created.data["id"])
    updated = client.put(
        f"/api/models/{project.public_id}/",
        {"name": "NIDS", "description": "latest", "access_mode": "public"},
        format="multipart",
    )
    assert updated.status_code == 200
    assert updated.data["description"] == "latest"
    assert project.versions.count() == 0
    assert Build.objects.filter(project=project).count() == 0
    client.force_authenticate(other)
    assert client.get(f"/api/models/{project.public_id}/").status_code == 404


@pytest.mark.django_db
def test_manual_build_upload_creates_immutable_build_snapshot(monkeypatch, django_capture_on_commit_callbacks):
    storage = FakeStorage()
    queued = []
    monkeypatch.setattr("apps.deployment.services.builds.S3Storage", lambda: storage)
    monkeypatch.setattr(
        "apps.deployment.services.builds.execute_build.delay",
        lambda build_id: queued.append(build_id) or SimpleNamespace(id="task-id"),
    )
    owner = get_user_model().objects.create_user("build-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="NIDS")
    client = APIClient()
    client.force_authenticate(owner)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            f"/api/models/{project.public_id}/builds/",
            {
                "flavor": "xgboost",
                "artifact_format": "raw",
                "requirements_text": "xgboost==2.1.0",
                "source_artifact": SimpleUploadedFile("model.xgb", b"model", "application/octet-stream"),
                "metrics_file": SimpleUploadedFile("metrics.json", b"{}", "application/json"),
            },
            format="multipart",
        )
    assert response.status_code == 201
    build = Build.objects.get(public_id=response.data["id"])
    assert build.version_id is None
    assert build.flavor == "xgboost"
    assert build.requirements_snapshot == "xgboost==2.1.0"
    assert set(build.input_assets.values_list("kind", flat=True)) == {"source_artifact", "metrics"}
    assert all(str(build.public_id) in uri for uri in build.input_assets.values_list("s3_uri", flat=True))
    assert queued == [str(build.public_id)]


@pytest.mark.django_db
def test_manual_build_rejects_incompatible_artifact_and_cross_tenant_access(monkeypatch):
    monkeypatch.setattr("apps.deployment.services.builds.S3Storage", FakeStorage)
    owner = get_user_model().objects.create_user("format-owner@example.com", "password123")
    other = get_user_model().objects.create_user("format-other@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="NIDS")
    client = APIClient()
    client.force_authenticate(owner)
    invalid = client.post(
        f"/api/models/{project.public_id}/builds/",
        {"flavor": "sklearn", "artifact_format": "raw", "source_artifact": SimpleUploadedFile("model.pt", b"model")},
        format="multipart",
    )
    assert invalid.status_code == 400
    client.force_authenticate(other)
    denied = client.post(
        f"/api/models/{project.public_id}/builds/",
        {"flavor": "sklearn", "source_artifact": SimpleUploadedFile("model.pkl", b"model")},
        format="multipart",
    )
    assert denied.status_code == 404
    assert not BuildInputAsset.objects.filter(build__project=project).exists()
