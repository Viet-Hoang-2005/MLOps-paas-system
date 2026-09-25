from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from apps.catalog.models import DraftAsset, ModelProject
from apps.catalog.services.draft import (
    dispatch_draft_build,
    ensure_project_draft,
    save_draft,
)
from apps.deployment.models import Build
from apps.deployment.tasks import cleanup_failed_build_artifacts
from apps.registry.services.versions import register_successful_build


class FakeStorage:
    def __init__(self, bucket="test-bucket"):
        self.bucket = bucket

    def copy(self, src_uri, dst_key):
        dst_uri = dst_key if dst_key.startswith("s3://") else f"s3://{self.bucket}/{dst_key}"
        return SimpleNamespace(
            uri=dst_uri,
            checksum="abc123sha256",
            size_bytes=2048,
            content_type="application/octet-stream",
        )

    def delete(self, uri):
        pass

    def delete_prefix(self, prefix):
        pass


class FakeImageRegistry:
    def promote(self, *, build, version, image_uri, image_digest=""):
        return f"harbor.local/user/{version.project.name}:{version.version}", image_digest or "sha256:builddigest"


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("be-build-owner@example.com", "password123")


@pytest.fixture
def project(owner):
    return ModelProject.objects.create(
        owner=owner,
        name="Build Lifecycle Project",
        description="Testing draft build lifecycle",
        task_domain="binary_classification",
    )


@pytest.fixture
def fake_storage():
    return FakeStorage()


@pytest.fixture
def fake_registry():
    return FakeImageRegistry()


@pytest.mark.django_db
def test_draft_build_locking_idempotency(project, owner, fake_storage):
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
    save_draft(draft=draft, expected_revision=draft.revision, storage=fake_storage)

    with patch("apps.catalog.services.draft.execute_build.delay"):
        build1 = dispatch_draft_build(draft=draft, actor=owner, storage=fake_storage)

    draft.refresh_from_db()
    assert draft.status == "locked"
    assert draft.locked_by_build == build1

    # Yêu cầu build thứ hai bị từ chối do Draft đang locked
    with pytest.raises(ValidationError) as exc:
        dispatch_draft_build(draft=draft, actor=owner, storage=fake_storage)
    assert "locked" in str(exc.value).lower()
    assert Build.objects.filter(project=project).count() == 1


@pytest.mark.django_db
def test_build_failure_unlocks_draft(project, owner, fake_storage):
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
    save_draft(draft=draft, expected_revision=draft.revision, storage=fake_storage)
    initial_revision = draft.revision

    with patch("apps.catalog.services.draft.execute_build.delay"):
        build = dispatch_draft_build(draft=draft, actor=owner, storage=fake_storage)

    draft.refresh_from_db()
    assert draft.status == "locked"

    # Giả lập worker Celery dọn dẹp và xử lý build thất bại
    with patch("apps.deployment.tasks.S3Storage", return_value=fake_storage):
        cleanup_failed_build_artifacts(str(build.public_id))

    draft.refresh_from_db()
    assert draft.status in {"editing", "ready"}
    assert draft.locked_by_build is None
    assert draft.revision == initial_revision


@pytest.mark.django_db
def test_build_success_creates_version_and_resets_draft(
    project, owner, fake_storage, fake_registry, django_capture_on_commit_callbacks
):
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
    save_draft(draft=draft, expected_revision=draft.revision, storage=fake_storage)

    with patch("apps.catalog.services.draft.execute_build.delay"):
        build = dispatch_draft_build(draft=draft, actor=owner, storage=fake_storage)

    with django_capture_on_commit_callbacks(execute=True):
        build = register_successful_build(
            build=build,
            image_uri="harbor.local/user/fraud:v1.0.0",
            image_digest="sha256:digest123",
            storage=fake_storage,
            image_registry=fake_registry,
        )

    version = build.version
    assert version is not None
    assert version.project == project
    assert version.reference_snapshot is not None

    draft.refresh_from_db()
    assert draft.status == "ready"
    assert draft.locked_by_build is None
    assert draft.saved_revision == draft.revision
