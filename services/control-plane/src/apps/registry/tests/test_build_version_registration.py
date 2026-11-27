from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

from apps.catalog.models import ModelProject
from apps.deployment.models import Build, BuildInputAsset
from apps.deployment.services.completion import request_registration
from apps.deployment.tasks import cleanup_registered_build_storage, reconcile_stalled_deletions
from apps.registry.models import ModelArtifact, ModelVersion
from apps.registry.services.deletion import delete_model_version, request_model_version_deletion
from apps.registry.services.versions import register_successful_build
from infrastructure.storage.paths import build_prefix
from infrastructure.storage.s3 import StoredObject


class FakeCopyStorage:
    bucket = "test-bucket"

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
        image_uri=f"image-{project.public_id}:temporary",
    )
    BuildInputAsset.objects.create(
        build=build,
        kind="source_artifact",
        name=name,
        s3_uri=f"s3://bucket/{build.public_id}/{name}",
    )
    return build


@pytest.mark.django_db
def test_successful_manual_build_registers_one_version_and_is_idempotent(django_capture_on_commit_callbacks, monkeypatch):
    monkeypatch.setattr(cleanup_registered_build_storage, "delay", Mock())
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


@pytest.mark.django_db
def test_registration_schedules_purge_after_commit_and_keeps_version_artifacts(
    monkeypatch, django_capture_on_commit_callbacks
):
    project, build = _project_and_build("reg-purge-build@example.com")
    prefix = f"{build_prefix(project.owner.tenant_id, project.public_id, build.public_id)}/"
    build.package_uri = f"s3://test-bucket/{prefix}artifacts/model-package.zip"
    build.save(update_fields=["package_uri"])
    storage = RecordingStorage()
    storage.delete_prefix = Mock()
    monkeypatch.setattr("apps.deployment.tasks.S3Storage", lambda: storage)
    dispatch = Mock(side_effect=cleanup_registered_build_storage.run)
    monkeypatch.setattr(cleanup_registered_build_storage, "delay", dispatch)

    with django_capture_on_commit_callbacks(execute=True):
        _register(build, storage)
        build.refresh_from_db()
        assert build.registered_storage_cleanup_due_at is not None
        assert build.package_uri
        storage.delete_prefix.assert_not_called()

    dispatch.assert_called_once_with(str(build.public_id))
    storage.delete_prefix.assert_called_once_with(prefix)
    build.refresh_from_db()
    assert build.registered_storage_cleanup_due_at is None
    assert build.package_uri == ""
    asset = build.input_assets.get()
    assert asset.s3_uri == ""
    assert asset.purged_at is not None
    assert build.version.artifacts.filter(kind="package", name="model-package.zip").exists()
    assert build.version.artifacts.filter(kind="source", name="model.pkl").exists()


@pytest.mark.django_db
def test_registration_rollback_does_not_dispatch_cleanup(monkeypatch, django_capture_on_commit_callbacks):
    _, build = _project_and_build("reg-purge-rollback@example.com")
    dispatch = Mock()
    monkeypatch.setattr(cleanup_registered_build_storage, "delay", dispatch)
    with django_capture_on_commit_callbacks(execute=True), pytest.raises(RuntimeError, match="roll back"):
        with transaction.atomic():
            _register(build, RecordingStorage())
            raise RuntimeError("roll back")
    build.refresh_from_db()
    assert build.version_id is None
    assert build.registered_storage_cleanup_due_at is None
    dispatch.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("detach", [False, True])
def test_registered_build_cleanup_retries_after_storage_timeout(monkeypatch, detach):
    project, build = _project_and_build("reg-purge-retry@example.com")
    storage = RecordingStorage()
    storage.delete_prefix = Mock(side_effect=[TimeoutError("S3 timeout"), None])
    monkeypatch.setattr("apps.deployment.tasks.S3Storage", lambda: storage)

    registered = _register(build, storage)
    with pytest.raises(TimeoutError, match="S3 timeout"):
        cleanup_registered_build_storage.run(str(build.public_id))
    build.refresh_from_db()
    assert build.input_assets.get().s3_uri
    assert build.registered_storage_cleanup_due_at > timezone.now()
    assert cleanup_registered_build_storage.run(str(build.public_id)) == "not_due"

    if detach:
        monkeypatch.setattr("apps.registry.services.deletion.invalidate_model_server_cache", Mock())
        request_model_version_deletion(registered.version)
        delete_model_version(registered.version, storage=Mock(bucket=storage.bucket), image_remover=Mock())
        build.refresh_from_db()
        assert build.version_id is None
        assert build.registered_storage_cleanup_due_at is not None

    Build.objects.filter(pk=build.pk).update(registered_storage_cleanup_due_at=timezone.now() - timedelta(seconds=1))
    dispatch = Mock(side_effect=cleanup_registered_build_storage.run)
    monkeypatch.setattr(cleanup_registered_build_storage, "delay", dispatch)
    assert reconcile_stalled_deletions.run() == 1
    if not detach:
        assert request_registration(build).version_id == registered.version_id
    assert ModelVersion.objects.filter(project=project).count() == (0 if detach else 1)
    assert storage.delete_prefix.call_count == 2
    build.refresh_from_db()
    assert build.registered_storage_cleanup_due_at is None
    assert build.input_assets.get().s3_uri == ""


@pytest.mark.django_db
def test_backfill_schedules_legacy_registered_storage_and_worker_preserves_live_version_uri(monkeypatch):
    project, build = _project_and_build("legacy-reg-purge@example.com")
    _, unregistered = _project_and_build("unregistered-no-purge@example.com")
    version = ModelVersion.objects.create(project=project, version="1", flavor="sklearn")
    build.version = version
    build.save(update_fields=["version"])
    prefix = f"{build_prefix(project.owner.tenant_id, project.public_id, build.public_id)}/"
    ModelArtifact.objects.create(version=version, kind="source", name="model.pkl", uri=f"s3://test-bucket/{prefix}model.pkl")
    migration = import_module("apps.deployment.migrations.0004_build_registered_storage_cleanup")
    migration.schedule_registered_builds(apps, SimpleNamespace(connection=connection))
    build.refresh_from_db()
    unregistered.refresh_from_db()
    assert build.registered_storage_cleanup_due_at is not None
    assert unregistered.registered_storage_cleanup_due_at is None

    storage = RecordingStorage()
    storage.delete_prefix = Mock()
    monkeypatch.setattr("apps.deployment.tasks.S3Storage", lambda: storage)
    with pytest.raises(RuntimeError, match="still referenced"):
        cleanup_registered_build_storage.run(str(build.public_id))
    storage.delete_prefix.assert_not_called()
    assert build.input_assets.get().s3_uri
