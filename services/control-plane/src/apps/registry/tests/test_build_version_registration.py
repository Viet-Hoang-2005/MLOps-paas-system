import pytest
from django.contrib.auth import get_user_model
from infrastructure.storage.s3 import StoredObject

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, BuildInputAsset
from apps.registry.models import ModelArtifact, ModelVersion
from apps.registry.services.versions import register_successful_build


class FakeCopyStorage:
    def copy(self, source_uri, destination_key):
        return StoredObject(
            destination_key,
            f"s3://test-bucket/{destination_key}",
            "checksum",
            12,
            "application/octet-stream",
        )

    def delete_prefix(self, prefix):
        return prefix


class FakeImageRegistry:
    def promote(self, *, build, version, image_uri, image_digest=""):
        return f"image-{build.project.public_id}:v{version.version}", image_digest or "sha256:local"


def build_for(project, name="model.pkl"):
    build = Build.objects.create(
        project=project,
        flavor="sklearn",
        requirements_snapshot="numpy==1.26.4",
        status="building",
    )
    BuildInputAsset.objects.create(
        build=build,
        kind="source_artifact",
        name=name,
        s3_uri=f"s3://bucket/{build.public_id}/{name}",
    )
    return build


@pytest.mark.django_db
def test_successful_manual_build_registers_one_version_and_is_idempotent(django_capture_on_commit_callbacks):
    user = get_user_model().objects.create_user("version-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")
    build = build_for(project)
    storage = FakeCopyStorage()
    with django_capture_on_commit_callbacks(execute=True):
        first = register_successful_build(
            build=build,
            image_uri=f"image-{project.public_id}:build-{build.public_id}",
            image_digest="sha256:first",
            storage=storage,
            image_registry=FakeImageRegistry(),
        )
    with django_capture_on_commit_callbacks(execute=True):
        replay = register_successful_build(
            build=build,
            image_uri=f"image-{project.public_id}:build-{build.public_id}",
            image_digest="sha256:first",
            storage=storage,
            image_registry=FakeImageRegistry(),
        )
    assert first.version_id == replay.version_id
    assert ModelVersion.objects.filter(project=project).count() == 1
    version = ModelVersion.objects.get(project=project)
    assert version.version == "1"
    assert version.artifacts.get(kind="source").name == "model.pkl"
    assert ModelArtifact.objects.get(version=version, kind="image").checksum == "sha256:first"


@pytest.mark.django_db
def test_each_successful_manual_build_allocates_next_version():
    user = get_user_model().objects.create_user("version-next@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")
    storage = FakeCopyStorage()
    first = build_for(project, "first.pkl")
    second = build_for(project, "second.pkl")
    first = register_successful_build(
        build=first,
        image_uri=f"image-{project.public_id}:build-{first.public_id}",
        storage=storage,
        image_registry=FakeImageRegistry(),
    )
    second = register_successful_build(
        build=second,
        image_uri=f"image-{project.public_id}:build-{second.public_id}",
        storage=storage,
        image_registry=FakeImageRegistry(),
    )
    assert first.version.version == "1"
    assert second.version.version == "2"
    project.refresh_from_db()
    assert project.next_version_number == 3
