from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from apps.catalog.models import DraftAsset, ModelProject
from apps.catalog.services.draft import ensure_project_draft
from apps.deployment.services.builds import request_training_build
from apps.registry.services.versions import register_successful_build
from apps.training.models import TrainingJob, TrainingOutput


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
    return get_user_model().objects.create_user("be-training-owner@example.com", "password123")


@pytest.fixture
def project(owner):
    return ModelProject.objects.create(
        owner=owner,
        name="Retraining Pipeline Project",
        description="Testing training runner integration and reference data contract",
        task_domain="binary_classification",
    )


@pytest.fixture
def fake_storage():
    return FakeStorage()


@pytest.fixture
def fake_registry():
    return FakeImageRegistry()


@pytest.mark.django_db
def test_training_build_does_not_mutate_draft(
    project, owner, fake_storage, fake_registry, django_capture_on_commit_callbacks
):
    draft = ensure_project_draft(project=project)
    DraftAsset.objects.create(
        draft=draft,
        kind="model",
        name="draft_model.joblib",
        s3_uri="s3://test-bucket/draft/draft_model.joblib",
        checksum="sha256:draft123",
        size_bytes=1024,
    )
    draft.revision = 5
    draft.status = "editing"
    draft.save()

    # Tạo training job hoàn tất với cả model và reference data
    job = TrainingJob.objects.create(
        project=project,
        name="Continuous Training Run",
        status="completed",
        model_flavor="sklearn",
        requirements_text="scikit-learn==1.4.0",
    )
    TrainingOutput.objects.create(
        job=job,
        kind="model",
        relative_path="model.tar.gz",
        s3_uri="s3://test-bucket/training/model.tar.gz",
        checksum="sha256:training_model",
        size_bytes=2048,
    )
    TrainingOutput.objects.create(
        job=job,
        kind="reference_data",
        relative_path="reference.parquet",
        s3_uri="s3://test-bucket/training/reference.parquet",
        checksum="sha256:training_ref",
        size_bytes=4096,
    )

    with patch("apps.deployment.services.builds._enqueue"):
        training_build, _ = request_training_build(job=job, backend="docker", storage=fake_storage)

    with django_capture_on_commit_callbacks(execute=True):
        build = register_successful_build(
            build=training_build,
            image_uri="harbor.local/user/fraud:v2.0.0",
            image_digest="sha256:train200",
            storage=fake_storage,
            image_registry=fake_registry,
        )

    version = build.version
    assert version is not None
    assert version.project == project

    # Bàn làm việc ModelDraft của người dùng tuyệt đối không bị can thiệp
    draft.refresh_from_db()
    assert draft.revision == 5
    assert draft.status == "editing"
    assert draft.locked_by_build is None
    assert draft.assets.filter(name="draft_model.joblib").exists()


@pytest.mark.django_db
def test_training_output_mandatory_reference(project, fake_storage):
    job = TrainingJob.objects.create(
        project=project,
        name="Job Without Reference",
        status="completed",
        model_flavor="sklearn",
    )
    TrainingOutput.objects.create(
        job=job,
        kind="model",
        relative_path="model.tar.gz",
        s3_uri="s3://test-bucket/training/model.tar.gz",
    )

    with pytest.raises(ValidationError) as exc:
        request_training_build(job=job, backend="docker", storage=fake_storage)
    assert "reference_data" in str(exc.value)
