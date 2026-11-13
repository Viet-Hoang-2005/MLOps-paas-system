import pytest
from django.contrib.auth import get_user_model

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, BuildInputAsset
from apps.registry.models import ModelArtifact, ModelVersion
from apps.registry.services.versions import register_successful_build
from infrastructure.storage.s3 import StoredObject


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
        status="ready",
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


class RecordingStorage(FakeCopyStorage):
    """Records copies and deletions; ``on_copy`` runs before each copy."""

    def __init__(self, on_copy=None):
        self.copied = []
        self.deleted = []
        self.on_copy = on_copy

    def copy(self, source_uri, destination_key):
        if self.on_copy:
            self.on_copy()
        stored = super().copy(source_uri, destination_key)
        self.copied.append(stored.uri)
        return stored

    def delete(self, uri):
        self.deleted.append(uri)


def _project_and_build(email):
    user = get_user_model().objects.create_user(email, "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")
    return project, build_for(project)


def _register(build, storage, registry=None):
    return register_successful_build(
        build=build,
        image_uri=f"image-{build.project.public_id}:build-{build.public_id}",
        image_digest="sha256:abc",
        storage=storage,
        image_registry=registry or FakeImageRegistry(),
    )


class _TransactionDepth:
    """Counts open ``transaction.atomic`` blocks created by the registry service."""

    def __init__(self, monkeypatch):
        import apps.registry.services.versions as module

        self.depth = 0
        real_atomic = module.transaction.atomic
        outer = self

        class Counting:
            def __init__(self, *args, **kwargs):
                self.inner = real_atomic(*args, **kwargs)

            def __enter__(self):
                outer.depth += 1
                return self.inner.__enter__()

            def __exit__(self, *exc):
                outer.depth -= 1
                return self.inner.__exit__(*exc)

        monkeypatch.setattr(module.transaction, "atomic", Counting)


@pytest.mark.django_db
def test_registration_holds_no_transaction_while_copying_or_promoting(monkeypatch):
    project, build = _project_and_build("reg-lock@example.com")
    tracker = _TransactionDepth(monkeypatch)

    def assert_no_transaction():
        assert tracker.depth == 0, "network call made inside a transaction"

    class CheckedRegistry(FakeImageRegistry):
        def promote(self, **kwargs):
            assert_no_transaction()
            return super().promote(**kwargs)

    _register(build, RecordingStorage(on_copy=assert_no_transaction), CheckedRegistry())

    assert ModelVersion.objects.filter(project=project).count() == 1


@pytest.mark.django_db
def test_failed_promotion_removes_copies_and_releases_the_version_number():
    project, build = _project_and_build("reg-fail@example.com")
    storage = RecordingStorage()

    class BrokenRegistry:
        def promote(self, **kwargs):
            raise RuntimeError("harbor unavailable")

    with pytest.raises(RuntimeError, match="harbor unavailable"):
        _register(build, storage, BrokenRegistry())

    project.refresh_from_db()
    build.refresh_from_db()
    assert storage.copied and sorted(storage.deleted) == sorted(storage.copied)
    assert not ModelVersion.objects.filter(project=project).exists()
    assert project.next_version_number == 1
    assert build.version_id is None

    # A retry succeeds and still gets version 1.
    _register(build, RecordingStorage())
    assert ModelVersion.objects.get(project=project).version == "1"


@pytest.mark.django_db
def test_project_deleted_while_copying_discards_the_registration():
    from rest_framework.exceptions import ValidationError

    project, build = _project_and_build("reg-deleted@example.com")

    def project_gets_deleted():
        ModelProject.objects.filter(pk=project.pk).update(deletion_state="deleting")

    storage = RecordingStorage(on_copy=project_gets_deleted)
    with pytest.raises(ValidationError):
        _register(build, storage)

    assert storage.copied and sorted(storage.deleted) == sorted(storage.copied)
    assert not ModelVersion.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_concurrent_registration_that_finishes_first_wins_and_ours_is_discarded():
    project, build = _project_and_build("reg-race@example.com")
    winner = {}

    def competitor_registers():
        if winner:
            return
        winner["version"] = ModelVersion.objects.create(project=project, version="1", flavor="sklearn")
        Build.objects.filter(pk=build.pk).update(version=winner["version"], registration_status="registered")

    storage = RecordingStorage(on_copy=competitor_registers)
    result = _register(build, storage)

    assert result.version_id == winner["version"].pk
    assert ModelVersion.objects.filter(project=project).count() == 1
    assert storage.copied and sorted(storage.deleted) == sorted(storage.copied)
    project.refresh_from_db()
    assert project.next_version_number == 1


@pytest.mark.django_db
def test_registration_is_skipped_while_another_attempt_holds_the_build():
    from django.core.cache import cache

    _project, build = _project_and_build("reg-busy@example.com")
    storage = RecordingStorage()
    cache.add(f"register-build:{build.pk}", 1, timeout=60)
    try:
        result = _register(build, storage)
    finally:
        cache.delete(f"register-build:{build.pk}")

    assert result.version_id is None
    assert storage.copied == []


@pytest.mark.django_db
def test_build_is_marked_registering_during_the_unlocked_phase():
    project, build = _project_and_build("reg-status@example.com")
    seen = {}

    def observe():
        seen["status"] = Build.objects.get(pk=build.pk).registration_status

    _register(build, RecordingStorage(on_copy=observe))

    # Build deletion and rebuild refuse to touch a registering build.
    assert seen["status"] == "registering"
    build.refresh_from_db()
    assert build.registration_status == "registered"
