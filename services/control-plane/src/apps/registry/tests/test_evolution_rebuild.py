from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.catalog.models import ModelProject
from apps.ct.models import DatasetSnapshot
from apps.deployment.models import Build, BuildInputAsset
from apps.registry.models import ModelArtifact, ModelVersion
from apps.registry.services.versions import (
    register_successful_build,
    request_version_rebuild,
)


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
    return get_user_model().objects.create_user("be-evolution-owner@example.com", "password123")


@pytest.fixture
def project(owner):
    return ModelProject.objects.create(
        owner=owner,
        name="Evolution Model Project",
        description="Testing evolution rebuild and webhook idempotency",
        task_domain="binary_classification",
    )


@pytest.fixture
def fake_storage():
    return FakeStorage()


@pytest.fixture
def fake_registry():
    return FakeImageRegistry()


@pytest.mark.django_db
def test_evolution_rebuild_clones_all_artifacts(project, owner, fake_storage):
    ref_snap = DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://test-bucket/ref/manifest.json",
        manifest_checksum="sha256:ref123",
        schema_checksum="sha256:schema123",
        row_count=1000,
    )
    version = ModelVersion.objects.create(
        project=project,
        version="v1.0.0",
        reference_snapshot=ref_snap,
        metrics_summary={"roc_auc": 0.94},
        params_summary={"hidden_sizes": [64, 32]},
        insights_summary={"source": "test"},
    )
    ModelArtifact.objects.create(
        version=version,
        kind="model",
        name="model.joblib",
        uri="s3://test-bucket/v1/model.joblib",
    )
    ModelArtifact.objects.create(
        version=version,
        kind="source_code",
        name="handler.zip",
        uri="s3://test-bucket/v1/handler.zip",
    )
    ModelArtifact.objects.create(
        version=version,
        kind="reference_data",
        name="reference.parquet",
        uri="s3://test-bucket/v1/reference.parquet",
    )
    ModelArtifact.objects.create(version=version, kind="package", name="package.zip", uri="s3://test-bucket/v1/package.zip")
    ModelArtifact.objects.create(version=version, kind="image", name="image", uri="registry/image@sha256:abc")

    with patch("apps.deployment.services.builds._enqueue"):
        rebuild = request_version_rebuild(version=version, actor=owner, backend="docker", storage=fake_storage)

    assert rebuild.source_kind == "model_version"
    assert rebuild.source_version == version

    input_kinds = set(rebuild.input_assets.values_list("kind", flat=True))
    assert "model" in input_kinds
    assert "source_code" in input_kinds
    assert "reference_data" in input_kinds
    assert "package" not in input_kinds
    assert "image" not in input_kinds
    assert rebuild.metrics_summary == version.metrics_summary
    assert rebuild.params_summary == version.params_summary
    assert rebuild.insights_summary == version.insights_summary


@pytest.mark.django_db
def test_webhook_callback_replay_safety(project, fake_storage, fake_registry, django_capture_on_commit_callbacks):
    snapshot = DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://test-bucket/ref.parquet",
        manifest_checksum="ref",
        schema_checksum="schema",
    )
    source_version = ModelVersion.objects.create(project=project, version="source", reference_snapshot=snapshot)
    build = Build.objects.create(
        project=project,
        source_version=source_version,
        flavor="sklearn",
        status="building",
    )
    BuildInputAsset.objects.create(
        build=build,
        kind="model",
        name="model.joblib",
        s3_uri="s3://test-bucket/model.joblib",
    )
    BuildInputAsset.objects.create(
        build=build,
        kind="reference_data",
        name="ref.parquet",
        s3_uri="s3://test-bucket/ref.parquet",
    )

    with django_capture_on_commit_callbacks(execute=True):
        first_build = register_successful_build(
            build=build,
            image_uri="harbor.local/user/fraud:v1.0.0",
            image_digest="sha256:first",
            storage=fake_storage,
            image_registry=fake_registry,
        )

    # Replay lần 2 với cùng build
    with django_capture_on_commit_callbacks(execute=True):
        second_build = register_successful_build(
            build=build,
            image_uri="harbor.local/user/fraud:v1.0.0",
            image_digest="sha256:first",
            storage=fake_storage,
            image_registry=fake_registry,
        )

    assert first_build.version.id == second_build.version.id
    assert ModelVersion.objects.filter(project=project).exclude(public_id=source_version.public_id).count() == 1
