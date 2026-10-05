from types import SimpleNamespace
from unittest.mock import Mock

import docker.errors
import pytest
from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject, PreviewAsset
from apps.deployment.models import Build, BuildInputAsset
from apps.deployment.services.builds import request_build_deletion, request_rebuild
from apps.deployment.services.completion import request_registration
from apps.deployment.tasks import delete_build, execute_build
from apps.registry.models import ModelVersion
from apps.training.models import TrainingJob, TrainingOutput
from common.api.exceptions import Conflict
from infrastructure.execution.build_cleanup import stop_build_for_deletion
from infrastructure.execution.image_cleanup import BuildImageCleaner
from infrastructure.storage.paths import build_prefix


@pytest.fixture
def project(db):
    owner = get_user_model().objects.create_user("build-actions@example.test", "test-password")
    return ModelProject.objects.create(owner=owner, name="Build actions")


@pytest.fixture
def cleanup(monkeypatch):
    stop, cleaner, storage = Mock(), Mock(), Mock()
    monkeypatch.setattr("apps.deployment.tasks.stop_build_for_deletion", stop)
    monkeypatch.setattr("apps.deployment.tasks.BuildImageCleaner", lambda: cleaner)
    monkeypatch.setattr("apps.deployment.tasks.S3Storage", lambda: storage)
    return stop, cleaner, storage


@pytest.mark.parametrize("state", ["pending", "queued", "building", "ready", "failed", "cancelled"])
def test_delete_accepts_every_unregistered_build(project, state, monkeypatch, django_capture_on_commit_callbacks):
    build = Build.objects.create(project=project, flavor="sklearn", status=state)
    enqueue = Mock()
    monkeypatch.setattr(delete_build, "delay", enqueue)
    client = APIClient()
    client.force_authenticate(project.owner)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete(f"/api/builds/{build.public_id}/")
    assert response.status_code == 202
    assert response.data["deletion_state"] == "deleting"
    enqueue.assert_called_once_with(str(build.public_id))
    build.refresh_from_db()
    assert build.status == state  # Preserve execution state until cleanup is confirmed.


@pytest.mark.parametrize("action", ["delete", "rebuild"])
def test_build_actions_do_not_enumerate_other_tenants(project, action):
    build = Build.objects.create(project=project, flavor="sklearn", status="ready")
    client = APIClient()
    other = get_user_model().objects.create_user("other-build-actions@example.test", "test-password")
    client.force_authenticate(other)
    url = f"/api/builds/{build.public_id}/"
    response = client.delete(url) if action == "delete" else client.post(f"{url}rebuild/")
    assert response.status_code == 404
    build.refresh_from_db()
    assert build.deletion_state == "active"


@pytest.mark.parametrize("registration", ["registering", "registered", "version"])
def test_registered_build_is_protected(project, registration):
    build = Build.objects.create(project=project, flavor="sklearn", status="ready")
    if registration == "version":
        build.version = ModelVersion.objects.create(project=project, version="1")
    else:
        build.registration_status = registration
    build.save()
    client = APIClient()
    client.force_authenticate(project.owner)
    assert client.delete(f"/api/builds/{build.public_id}/").status_code == 409
    assert Build.objects.filter(pk=build.pk).exists()


def test_delete_is_idempotent_and_retryable(project, monkeypatch, django_capture_on_commit_callbacks):
    build = Build.objects.create(project=project, flavor="sklearn", status="ready")
    enqueue = Mock()
    monkeypatch.setattr(delete_build, "delay", enqueue)
    with django_capture_on_commit_callbacks(execute=True):
        request_build_deletion(build)
        request_build_deletion(build)
    assert enqueue.call_count == 1
    Build.objects.filter(pk=build.pk).update(deletion_state="delete_failed")
    with django_capture_on_commit_callbacks(execute=True):
        request_build_deletion(build)
    assert enqueue.call_count == 2


@pytest.mark.parametrize("state", ["ready", "failed", "building"])
def test_cleanup_hard_deletes_after_image_and_storage_cleanup(project, cleanup, state):
    build = Build.objects.create(
        project=project,
        flavor="sklearn",
        status=state,
        deletion_state="deleting",
        image_uri="some-other-project:v1",  # Never trust a stale/reporter-supplied reference.
    )
    BuildInputAsset.objects.create(build=build, kind="source_artifact", name="model.pkl")
    stop, cleaner, storage = cleanup
    expected = f"image-{project.public_id}:build-{build.public_id}"
    seen = []
    cleaner.delete.side_effect = lambda selected: seen.append(selected.image_uri)
    assert delete_build.run(str(build.public_id)) == "deleted"
    stop.assert_called_once()
    assert seen == [expected]
    storage.delete_prefix.assert_called_once_with(
        f"{build_prefix(project.owner.tenant_id, project.public_id, build.public_id).rstrip('/')}/"
    )
    assert not Build.objects.filter(pk=build.pk).exists()
    assert not BuildInputAsset.objects.filter(build_id=build.pk).exists()
    assert ModelProject.objects.filter(pk=project.pk).exists()
    assert delete_build.run(str(build.public_id)) == "deleted"


def test_cleanup_failure_retains_retryable_record(project, cleanup, monkeypatch):
    build = Build.objects.create(project=project, flavor="sklearn", status="ready", deletion_state="deleting")
    _, cleaner, storage = cleanup
    cleaner.delete.side_effect = RuntimeError("registry temporarily unavailable")
    monkeypatch.setattr(delete_build, "retry", Mock(side_effect=Retry()))
    with pytest.raises(Retry):
        delete_build.run(str(build.public_id))
    build.refresh_from_db()
    assert build.deletion_state == "delete_failed"
    storage.delete_prefix.assert_not_called()
    cleaner.delete.side_effect = None
    assert delete_build.run(str(build.public_id)) == "deleted"


def test_worker_rechecks_registration_before_touching_image(project, cleanup, monkeypatch):
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, flavor="sklearn", version=version, deletion_state="deleting")
    monkeypatch.setattr(delete_build, "retry", Mock(side_effect=Retry()))
    with pytest.raises(Retry):
        delete_build.run(str(build.public_id))
    stop, cleaner, storage = cleanup
    stop.assert_not_called()
    cleaner.delete.assert_not_called()
    storage.delete_prefix.assert_not_called()


def test_deletion_blocks_registration_and_queued_execution(project, monkeypatch):
    build = Build.objects.create(project=project, flavor="sklearn", status="ready", deletion_state="deleting")
    with pytest.raises(Conflict):
        request_registration(build)
    backend = Mock()
    monkeypatch.setattr("apps.deployment.tasks.build_backend", backend)
    assert execute_build.run(str(build.public_id)) == "deleting"
    backend.assert_not_called()
    build.delete()
    assert execute_build.run(str(build.public_id)) == "not_found"


def test_local_cleanup_removes_only_known_build_container(project, monkeypatch):
    build = Build.objects.create(project=project, flavor="sklearn", backend="docker")
    client = Mock()
    monkeypatch.setattr("infrastructure.execution.build_cleanup.DockerClient", lambda: SimpleNamespace(client=client))
    stop_build_for_deletion(build)
    client.containers.get.assert_called_once_with(f"build-{build.public_id}")
    client.containers.get.return_value.remove.assert_called_once_with(force=True)
    client.containers.get.side_effect = docker.errors.NotFound("already absent")
    stop_build_for_deletion(build)


def test_argo_cleanup_waits_for_trusted_terminal_callback_even_if_cancelled(project):
    build = Build.objects.create(
        project=project, flavor="sklearn", backend="argo", status="cancelled", started_at=timezone.now()
    )
    with pytest.raises(RuntimeError, match="Waiting"):
        stop_build_for_deletion(build)
    build.execution_completed_at = timezone.now()
    stop_build_for_deletion(build)


@pytest.mark.parametrize("status", ["building", "cancelled"])
def test_late_webhook_cannot_register_or_revive_deleted_build(
    project, monkeypatch, settings, status, django_capture_on_commit_callbacks
):
    settings.CONTROL_PLANE_WEBHOOK_SECRET = "test-webhook-secret"
    build = Build.objects.create(
        project=project, flavor="sklearn", backend="argo", status=status, deletion_state="deleting"
    )
    enqueue = Mock()
    monkeypatch.setattr(delete_build, "delay", enqueue)
    with django_capture_on_commit_callbacks(execute=True):
        response = APIClient().post(
            f"/internal/webhooks/builds/{build.public_id}/",
            {"status": "success"},
            format="json",
            HTTP_X_CONTROL_PLANE_SECRET="test-webhook-secret",
        )
    assert response.status_code == 200
    build.refresh_from_db()
    assert build.status == "cancelled"
    assert build.version_id is None
    assert build.execution_completed_at is not None
    enqueue.assert_called_once_with(str(build.public_id))


class CopyStorage:
    def __init__(self):
        self.copies = []

    def copy(self, uri, key):
        self.copies.append((uri, key))
        return SimpleNamespace(
            uri=f"s3://test-bucket/{key}", checksum="checksum", size_bytes=3, content_type="application/octet-stream"
        )


@pytest.mark.parametrize("status", ["failed", "ready", "cancelled"])
def test_rebuild_copies_current_preview_into_new_build(project, status, monkeypatch):
    project.preview.flavor = "xgboost"
    project.preview.revision = 3
    project.preview.save()
    PreviewAsset.objects.create(
        preview=project.preview, kind="source_artifact", name="current.pkl", s3_uri="s3://test-bucket/current.pkl"
    )
    original = Build.objects.create(project=project, flavor="sklearn", status=status, preview_revision=1)
    storage = CopyStorage()
    monkeypatch.setattr("apps.deployment.services.builds._enqueue", Mock())
    result = request_rebuild(original, backend="docker", storage=storage)
    assert result.pk != original.pk
    assert result.preview_revision == 3
    assert result.flavor == "xgboost"
    assert result.status == "queued"
    assert storage.copies[0][0] == "s3://test-bucket/current.pkl"
    original.refresh_from_db()
    assert original.status == status


def test_rebuild_uses_original_completed_training_job(project, monkeypatch):
    job = TrainingJob.objects.create(project=project, name="trained", model_flavor="xgboost", status="completed")
    TrainingOutput.objects.create(
        job=job, kind="model", relative_path="model.tar.gz", s3_uri="s3://test-bucket/trained.tar.gz"
    )
    original = Build.objects.create(
        project=project, source_job=job, source_job_reference=job.public_id, flavor="xgboost", status="failed"
    )
    storage = CopyStorage()
    monkeypatch.setattr("apps.deployment.services.builds._enqueue", Mock())
    result = request_rebuild(original, backend="docker", storage=storage)
    assert result.pk != original.pk
    assert result.source_job_id == job.pk
    assert storage.copies[0][0] == "s3://test-bucket/trained.tar.gz"
    job.delete()
    with pytest.raises(Conflict, match="deleted"):
        request_rebuild(original, backend="docker", storage=storage)


def test_rebuild_does_not_reuse_training_build_being_deleted(project):
    job = TrainingJob.objects.create(project=project, name="trained", model_flavor="xgboost", status="completed")
    original = Build.objects.create(project=project, source_job=job, flavor="xgboost", status="failed")
    Build.objects.create(
        project=project, source_job=job, flavor="xgboost", status="building", deletion_state="deleting"
    )
    with pytest.raises(Conflict, match="cleanup"):
        request_rebuild(original, backend="docker", storage=CopyStorage())


@pytest.mark.parametrize(
    "field,value", [("status", "building"), ("deletion_state", "deleting"), ("registration_status", "registering")]
)
def test_rebuild_rejects_busy_or_deleting_build(project, field, value):
    build = Build.objects.create(project=project, flavor="sklearn", status="ready")
    setattr(build, field, value)
    build.save()
    with pytest.raises(Conflict):
        request_rebuild(build, backend="docker", storage=CopyStorage())


def test_local_image_cleanup_does_not_force_remove_shared_layers():
    client = Mock()
    build = SimpleNamespace(image_uri="image-project:build-job", backend="docker")
    cleaner = BuildImageCleaner(docker_client=SimpleNamespace(client=client))
    assert cleaner.delete(build) == "deleted"
    client.images.remove.assert_called_once_with(build.image_uri, force=False, noprune=False)
    client.images.remove.side_effect = docker.errors.ImageNotFound("already absent")
    assert cleaner.delete(build) == "already-absent"
