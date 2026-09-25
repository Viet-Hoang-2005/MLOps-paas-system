import io
import tarfile
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import DraftAsset, ModelProject
from apps.ct.models import DatasetSnapshot
from apps.deployment.models import Build, Deployment, Endpoint
from apps.registry.models import ModelArtifact, ModelVersion, RegistryAlias


class FakeStorage:
    def __init__(self, bucket="test-bucket"):
        self.bucket = bucket
        self.files = {}
        self.client = SimpleNamespace(
            generate_presigned_url=Mock(return_value="https://s3.test/presigned-put-url"),
            head_object=Mock(
                return_value={
                    "ContentLength": 1024,
                    "ContentType": "application/octet-stream",
                    "Metadata": {"sha256": "a" * 64},
                }
            ),
        )

    def presigned_put(self, uri, expires_in=900, content_type=None, metadata=None):
        return f"https://s3.test/presigned-put-url?uri={uri}&expires={expires_in}"

    def presigned_get(self, uri, expires_in=900):
        return f"https://s3.test/presigned-get-url?uri={uri}&expires={expires_in}"

    def parse_uri(self, uri):
        if not uri.startswith("s3://"):
            raise ValueError("Expected an s3:// URI")
        parts = uri[5:].split("/", 1)
        return parts[0], parts[1]

    def head(self, uri):
        return {
            "ContentLength": 1024,
            "ContentType": "application/octet-stream",
            "Metadata": {"sha256": "a" * 64},
        }

    def download_fileobj(self, uri, f):
        content = self.files.get(uri, b"dummy-data")
        f.write(content)
        f.seek(0)

    def copy(self, src_uri, dst_key):
        if not dst_key.startswith("s3://"):
            dst_uri = f"s3://{self.bucket}/{dst_key}"
        else:
            dst_uri = dst_key
        return SimpleNamespace(
            key=dst_key,
            uri=dst_uri,
            checksum="fake-sha256",
            size_bytes=1024,
            content_type="application/octet-stream",
        )

    def delete_prefix(self, prefix):
        for uri in list(self.files):
            if uri.startswith(prefix):
                del self.files[uri]

    def delete(self, uri):
        self.files.pop(uri, None)

    def delete_prefix(self, prefix):
        keys_to_del = [k for k in self.files if k.startswith(prefix)]
        for k in keys_to_del:
            self.files.pop(k, None)


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("draft-owner@example.com", "password123")


@pytest.fixture
def stranger(db):
    return get_user_model().objects.create_user("draft-stranger@example.com", "password123")


@pytest.fixture
def project(owner):
    return ModelProject.objects.create(
        owner=owner,
        name="Diabetes PaaS",
        description="Predicting diabetes readmission",
        task_domain="binary_classification",
    )


@pytest.mark.django_db
def test_overview_endpoint_tenant_isolation(project, stranger, owner):
    client = APIClient()
    client.force_authenticate(stranger)
    res = client.get(f"/api/models/{project.public_id}/overview/")
    assert res.status_code == 404

    client.force_authenticate(owner)
    res = client.get(f"/api/models/{project.public_id}/overview/")
    assert res.status_code == 200
    data = res.data
    assert data["project"]["name"] == "Diabetes PaaS"
    assert data["present"]["has_production"] is False
    assert data["draft"]["status"] == "editing"
    assert data["draft"]["revision"] == 1
    assert data["candidate_versions"] == []


@pytest.mark.django_db
def test_overview_endpoint_with_production_alias(project, owner):
    # Setup production version
    ref_snap = DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://test-bucket/ref/manifest.json",
        manifest_checksum="sha256:ref123",
        schema_checksum="sha256:sch123",
        row_count=5000,
    )
    version = ModelVersion.objects.create(
        project=project,
        version="v1.0.0",
        reference_snapshot=ref_snap,
        metrics_summary={"roc_auc": 0.85, "f1": 0.82},
    )
    ModelArtifact.objects.create(
        version=version,
        kind="image",
        name="image",
        uri="harbor.mlops.local/library/diabetes:v1.0.0",
    )
    build = Build.objects.create(
        project=project,
        version=version,
        source_version=version,
        flavor="sklearn",
        status="ready",
    )
    deployment = Deployment.objects.create(
        project=project,
        version=version,
        build=build,
        target="production",
        status="healthy",
    )
    Endpoint.objects.create(
        deployment=deployment,
        public_url="https://models.mlops.local/v1/models/diabetes/predict",
        health_status="healthy",
    )
    RegistryAlias.objects.create(
        project=project,
        name="production",
        version=version,
    )

    client = APIClient()
    client.force_authenticate(owner)
    res = client.get(f"/api/models/{project.public_id}/overview/")
    assert res.status_code == 200
    present = res.data["present"]
    assert present["has_production"] is True
    assert present["version"] == "v1.0.0"
    assert present["image_uri"] == "harbor.mlops.local/library/diabetes:v1.0.0"
    assert present["endpoint_url"] == "https://models.mlops.local/v1/models/diabetes/predict"
    assert present["health_status"] == "healthy"
    assert present["reference_snapshot"]["row_count"] == 5000
    assert present["metrics"]["roc_auc"] == 0.85


@pytest.mark.django_db
def test_draft_detail_and_update(project, owner):
    client = APIClient()
    client.force_authenticate(owner)

    # GET Draft
    res = client.get(f"/api/models/{project.public_id}/draft/")
    assert res.status_code == 200
    assert res.data["revision"] == 1
    assert res.data["saved_revision"] == 0
    assert res.data["is_dirty"] is True

    # PUT Draft update
    res = client.patch(
        f"/api/models/{project.public_id}/draft/",
        {
            "expected_revision": 1,
            "flavor": "sklearn",
            "artifact_format": "raw",
            "requirements_snapshot": "scikit-learn==1.3.0\npandas==2.0.0",
        },
        format="json",
    )
    assert res.status_code == 200
    assert res.data["flavor"] == "sklearn"
    assert res.data["artifact_format"] == "raw"
    assert "scikit-learn==1.3.0" in res.data["requirements_snapshot"]
    assert res.data["revision"] == 2


@pytest.mark.django_db
@patch("apps.catalog.services.draft.S3Storage", FakeStorage)
@patch("infrastructure.storage.S3Storage", FakeStorage)
def test_draft_save_optimistic_concurrency(project, owner):
    client = APIClient()
    client.force_authenticate(owner)

    draft = project.current_draft
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
    current_rev = draft.revision

    # Save with wrong revision -> 409 Conflict
    res = client.post(
        f"/api/models/{project.public_id}/draft/save/",
        {"expected_revision": current_rev + 99},
        format="json",
    )
    assert res.status_code == 409

    # Save with matching revision -> 200 OK
    res = client.post(
        f"/api/models/{project.public_id}/draft/save/",
        {"expected_revision": current_rev},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["revision"] == current_rev
    assert res.data["saved_revision"] == current_rev
    assert res.data["is_dirty"] is False


@pytest.mark.django_db
@patch("apps.catalog.services.draft.S3Storage", FakeStorage)
@patch("infrastructure.storage.S3Storage", FakeStorage)
def test_draft_asset_upload_url_and_complete(project, owner):
    client = APIClient()
    client.force_authenticate(owner)

    # 1. Get presigned upload URL
    res = client.post(
        f"/api/models/{project.public_id}/draft/assets/upload-url/",
        {
            "kind": "model",
            "filename": "model.joblib",
            "content_type": "application/octet-stream",
            "size_bytes": 1024,
            "checksum": "a" * 64,
        },
        format="json",
    )
    assert res.status_code == 200
    assert "upload_url" in res.data
    assert "s3_uri" not in res.data
    upload_id = res.data["upload_id"]

    # 2. Complete upload
    res = client.post(
        f"/api/models/{project.public_id}/draft/assets/complete/",
        {
            "upload_id": upload_id,
        },
        format="json",
    )
    assert res.status_code == 201
    assert res.data["kind"] == "model"
    assert res.data["name"] == "model.joblib"

    # Verify draft revision incremented
    draft = project.current_draft
    assert draft.assets.count() == 1
    assert draft.revision > 1


@pytest.mark.django_db
@patch("apps.catalog.services.draft.S3Storage", FakeStorage)
def test_draft_asset_delete(project, owner):
    client = APIClient()
    client.force_authenticate(owner)

    draft = project.current_draft
    DraftAsset.objects.create(
        draft=draft,
        kind="source_code",
        name="train.py",
        s3_uri="s3://test-bucket/code/train.py",
    )
    assert draft.assets.filter(kind="source_code").exists()

    res = client.delete(f"/api/models/{project.public_id}/draft/assets/source_code/")
    assert res.status_code == 204
    assert not draft.assets.filter(kind="source_code").exists()


@pytest.mark.django_db
@patch("apps.catalog.services.draft.S3Storage", FakeStorage)
@patch("infrastructure.storage.S3Storage", FakeStorage)
def test_draft_build_validation_and_dispatch(project, owner, django_capture_on_commit_callbacks):
    client = APIClient()
    client.force_authenticate(owner)

    # Missing mandatory assets -> 400
    res = client.post(
        f"/api/models/{project.public_id}/draft/build/",
        {"backend": "docker"},
        format="json",
    )
    assert res.status_code == 400

    # Add mandatory assets
    draft = project.current_draft
    DraftAsset.objects.create(
        draft=draft,
        kind="model",
        name="model.joblib",
        s3_uri="s3://test-bucket/model.joblib",
    )
    DraftAsset.objects.create(
        draft=draft,
        kind="reference_data",
        name="ref.csv",
        s3_uri="s3://test-bucket/ref.csv",
    )

    # Draft is dirty (not saved) -> 400
    res = client.post(
        f"/api/models/{project.public_id}/draft/build/",
        {"backend": "docker"},
        format="json",
    )
    assert res.status_code == 400

    saved = client.post(
        f"/api/models/{project.public_id}/draft/save/",
        {"expected_revision": draft.revision},
        format="json",
    )
    assert saved.status_code == 200

    # Now dispatch build succeeds
    with patch("apps.catalog.services.draft.execute_build.delay") as mock_delay:
        with django_capture_on_commit_callbacks(execute=True):
            res = client.post(
                f"/api/models/{project.public_id}/draft/build/",
                {"backend": "docker"},
                format="json",
            )
        assert res.status_code == 201
        assert mock_delay.called

    # Draft is now locked
    draft.refresh_from_db()
    assert draft.status == "locked"
    assert draft.locked_by_build is not None

    # Editing locked draft should fail with 409
    res = client.put(
        f"/api/models/{project.public_id}/draft/",
        {"flavor": "xgboost", "expected_revision": draft.revision},
        format="json",
    )
    assert res.status_code == 409


@pytest.mark.django_db
@patch("apps.catalog.services.draft.S3Storage", FakeStorage)
@patch("infrastructure.storage.S3Storage", FakeStorage)
def test_draft_load_version(project, owner):
    client = APIClient()
    client.force_authenticate(owner)

    snapshot = DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://test-bucket/versions/v1/reference.parquet",
        manifest_checksum="ref-checksum",
        schema_checksum="schema-checksum",
    )
    version = ModelVersion.objects.create(
        project=project,
        version="v1.0.0",
        flavor="sklearn",
        reference_snapshot=snapshot,
    )
    ModelArtifact.objects.create(
        version=version,
        kind="model",
        name="model.joblib",
        uri="s3://test-bucket/versions/v1/model.joblib",
    )
    ModelArtifact.objects.create(
        version=version,
        kind="reference_data",
        name="reference.parquet",
        uri="s3://test-bucket/versions/v1/reference.parquet",
    )

    # Without confirm -> 400
    res = client.post(
        f"/api/models/{project.public_id}/draft/load-version/",
        {"version_id": str(version.public_id), "confirm": False},
        format="json",
    )
    assert res.status_code == 400

    # With confirm -> 200
    res = client.post(
        f"/api/models/{project.public_id}/draft/load-version/",
        {"version_id": str(version.public_id), "confirm": True},
        format="json",
    )
    assert res.status_code == 200
    draft = project.current_draft
    assert draft.flavor == "sklearn"
    assert draft.assets.filter(kind="model").exists()


def test_archive_security_path_traversal():
    from rest_framework.exceptions import ValidationError

    from apps.catalog.services.archive_validation import validate_tar_archive, validate_zip_archive

    # Create zip with directory traversal
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("../evil.sh", b"echo evil")
    zip_buf.seek(0)

    with pytest.raises(ValidationError) as exc:
        validate_zip_archive(zip_buf)
    assert "unsafe path" in str(exc.value).lower()

    # Create tar with directory traversal
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
        ti = tarfile.TarInfo(name="../../etc/passwd")
        ti.size = 9
        tf.addfile(ti, io.BytesIO(b"root:x:0:"))
    tar_buf.seek(0)

    with pytest.raises(ValidationError) as exc:
        validate_tar_archive(tar_buf)
    assert "unsafe path" in str(exc.value).lower()
