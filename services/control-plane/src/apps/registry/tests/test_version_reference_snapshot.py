import pytest
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError

from apps.catalog.models import ModelProject
from apps.ct.models import DatasetSnapshot
from apps.deployment.models import Build, BuildInputAsset
from apps.registry.models import ModelArtifact, ModelVersion
from apps.registry.services.versions import register_successful_build


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_user("registry-owner@example.com", "password123")


@pytest.fixture
def dummy_image_registry():
    class DummyRegistry:
        def promote(self, *, build, version, image_uri, image_digest=""):
            return f"harbor.local/user/{version.project.name}:{version.version}", "sha256:dummy123"

    return DummyRegistry()


@pytest.mark.django_db
def test_version_links_and_protects_reference_snapshot(owner):
    project = ModelProject.objects.create(owner=owner, name="Snapshot Project")
    snapshot = DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://bucket/manifest.json",
        manifest_checksum="sha256:abc",
        schema_checksum="sha256:def",
    )

    version = ModelVersion.objects.create(
        project=project,
        version="1",
        reference_snapshot=snapshot,
    )

    assert version.reference_snapshot == snapshot
    assert snapshot.model_versions.first() == version

    # ProtectedError when attempting to delete referenced snapshot
    with pytest.raises(ProtectedError):
        snapshot.delete()


@pytest.mark.django_db
def test_model_artifact_supports_new_kinds(owner):
    project = ModelProject.objects.create(owner=owner, name="Artifact Kinds Project")
    snapshot = DatasetSnapshot.objects.create(
        project=project, role="reference", manifest_uri="s3://bucket/ref", manifest_checksum="m", schema_checksum="s"
    )
    version = ModelVersion.objects.create(project=project, version="1", reference_snapshot=snapshot)

    for kind in ("model", "reference_data", "data_contract"):
        art = ModelArtifact.objects.create(
            version=version,
            kind=kind,
            name=f"{kind}.bin",
            uri=f"s3://bucket/{kind}.bin",
        )
        assert art.kind == kind


@pytest.mark.django_db
def test_register_successful_build_sets_registered_version_and_unlocks_draft(owner, dummy_image_registry, monkeypatch):
    class DummyStorage:
        def copy(self, src, dst):
            from types import SimpleNamespace
            return SimpleNamespace(uri=dst, checksum="sha256:copied", size_bytes=100, content_type="application/octet-stream")
        def delete_prefix(self, prefix):
            pass

    project = ModelProject.objects.create(owner=owner, name="Build Register Project")
    draft = project.current_draft

    from apps.catalog.models import DraftRevisionAsset, ModelDraftRevision
    from apps.ct.models import DatasetSnapshot

    snapshot = DatasetSnapshot.objects.create(
        project=project,
        role="reference",
        manifest_uri="s3://bucket/reference.parquet",
        manifest_checksum="ref",
        schema_checksum="schema",
    )
    revision = ModelDraftRevision.objects.create(draft=draft, number=1)
    DraftRevisionAsset.objects.create(
        revision=revision, kind="model", name="model.joblib", uri="s3://bucket/model.joblib"
    )
    DraftRevisionAsset.objects.create(
        revision=revision, kind="reference_data", name="reference.parquet", uri="s3://bucket/reference.parquet"
    )
    revision.source_version = None
    revision.save(update_fields=["source_version"])
    draft.saved_snapshot = revision
    draft.saved_revision = draft.revision
    draft.save(update_fields=["saved_snapshot", "saved_revision"])
    build = Build.objects.create(project=project, flavor="sklearn", source_draft_revision=revision)
    # Lock draft to build
    draft.locked_by_build = build
    draft.status = "locked"
    draft.save()

    BuildInputAsset.objects.create(
        build=build,
        kind="model",
        name="model.joblib",
        s3_uri="s3://bucket/builds/model.joblib",
    )
    BuildInputAsset.objects.create(
        build=build,
        kind="reference_data",
        name="reference.parquet",
        s3_uri="s3://bucket/builds/reference.parquet",
    )

    registered_build = register_successful_build(
        build=build,
        image_uri="build-temp:latest",
        storage=DummyStorage(),
        image_registry=dummy_image_registry,
    )

    assert registered_build.status == "ready"
    assert registered_build.version is not None
    assert registered_build.version.version == "1"
    assert registered_build.version.reference_snapshot_id is not None

    # Verify draft was unlocked
    draft.refresh_from_db()
    assert draft.locked_by_build is None
    assert draft.status == "ready"

    draft.flavor = "xgboost"
    draft.revision += 1
    draft.save(update_fields=["flavor", "revision"])
    replayed = register_successful_build(
        build=registered_build,
        image_uri="build-temp:latest",
        storage=DummyStorage(),
        image_registry=dummy_image_registry,
    )
    draft.refresh_from_db()
    assert replayed.version_id == registered_build.version_id
    assert draft.flavor == "xgboost"
