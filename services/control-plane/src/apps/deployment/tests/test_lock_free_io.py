"""Object-storage and runtime I/O never runs inside a transaction; stalled deletions are re-run."""

import hashlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.utils import timezone

from apps.catalog import tasks as catalog_tasks
from apps.catalog.models import ModelPreview, ModelProject
from apps.deployment import tasks
from apps.deployment.models import Build, BuildInputAsset
from apps.deployment.services import builds as build_service
from apps.training import tasks as training_tasks
from apps.training.models import TrainingJob, TrainingOutput
from apps.training.services import jobs as job_service
from common.api.exceptions import Conflict
from infrastructure.storage.s3 import StoredObject

pytestmark = pytest.mark.django_db(transaction=True)


class GuardedStorage:
    """In-memory storage that records any call made while a transaction is open."""

    bucket = "test-bucket"

    def __init__(self):
        self.objects = {}
        self.deleted = []
        self.inside_transaction = []
        self.on_copy = None
        self.fail_copy = False

    def _guard(self, operation):
        if connection.in_atomic_block:
            self.inside_transaction.append(operation)

    def parse_uri(self, uri):
        bucket, _, key = uri.removeprefix("s3://").partition("/")
        return bucket, key

    def put(self, key, file, content_type="application/octet-stream"):
        self._guard("put")
        payload = file.read() if hasattr(file, "read") else file
        uri = f"s3://{self.bucket}/{key}"
        self.objects[uri] = payload
        return StoredObject(key, uri, hashlib.sha256(payload).hexdigest(), len(payload), content_type)

    def copy(self, uri, key, **kwargs):
        self._guard("copy")
        if self.fail_copy:
            raise RuntimeError("storage unavailable")
        if self.on_copy:
            self.on_copy()
        payload = self.objects[uri]
        destination = f"s3://{self.bucket}/{key}"
        self.objects[destination] = payload
        return StoredObject(key, destination, hashlib.sha256(payload).hexdigest(), len(payload), "application/x")

    def read(self, uri, max_bytes=4 * 1024 * 1024):
        self._guard("read")
        return self.objects[uri]

    def delete_prefix(self, prefix):
        self._guard("delete_prefix")
        self.deleted.append(prefix)


@pytest.fixture
def project():
    owner = get_user_model().objects.create_user("lock-free@example.com", "test-password")
    return ModelProject.objects.create(owner=owner, name="lock-free")


@pytest.fixture
def storage():
    return GuardedStorage()


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    monkeypatch.setattr(tasks.execute_build, "delay", Mock(return_value=SimpleNamespace(id="task-1")))


def completed_job(project, storage):
    code = storage.put("input/code.zip", b"code")
    job = TrainingJob.objects.create(
        project=project,
        name="trained",
        model_flavor="xgboost",
        status="completed",
        entry_point="train.py",
        code_snapshot_uri=code.uri,
        data_snapshot_uri=code.uri,
    )
    for kind, name, payload in (
        ("model", "model.tar.gz", b"model"),
        ("source_code", "train.py", b"print(1)"),
        ("metric", "metrics.json", b'{"accuracy": 0.9}'),
    ):
        stored = storage.put(f"output/{name}", payload)
        TrainingOutput.objects.create(job=job, kind=kind, relative_path=name, s3_uri=stored.uri)
    return job


def draft_preview(project, storage):
    preview = ModelPreview.objects.get(project=project)
    ModelPreview.objects.filter(pk=preview.pk).update(flavor="xgboost", requirements_text="")
    for kind, name, payload in (("source_artifact", "model.pkl", b"m"), ("metrics", "metrics.json", b'{"a": 1}')):
        stored = storage.put(f"staging/{name}", payload)
        preview.assets.create(kind=kind, name=name, s3_uri=stored.uri)
    preview.refresh_from_db()
    return preview


# ---- builds -----------------------------------------------------------------------------------


def test_training_build_copies_inputs_outside_any_transaction(project, storage):
    job = completed_job(project, storage)
    build, created = build_service.request_training_build(job=job, backend="docker", storage=storage)
    assert created and build.status == "queued"
    assert storage.inside_transaction == []
    assert BuildInputAsset.objects.filter(build=build).count() == 2
    assert build.metrics_summary == {"accuracy": 0.9}
    tasks.execute_build.delay.assert_called_once_with(str(build.public_id))


def test_preview_build_copies_inputs_outside_any_transaction(project, storage):
    preview = draft_preview(project, storage)
    build = build_service.request_preview_build(
        project=project, revision=preview.revision, backend="docker", storage=storage
    )
    assert storage.inside_transaction == []
    assert build.status == "queued" and build.input_assets.count() == 2
    assert build.metrics_summary == {"a": 1}


def test_rebuild_copies_outside_any_transaction(project, storage):
    job = completed_job(project, storage)
    first, _ = build_service.request_training_build(job=job, backend="docker", storage=storage)
    Build.objects.filter(pk=first.pk).update(status="failed")
    storage.inside_transaction.clear()
    again = build_service.request_rebuild(first, backend="docker", storage=storage)
    assert again.pk != first.pk
    assert storage.inside_transaction == []


def test_failed_copy_leaves_no_build_and_removes_staged_inputs(project, storage):
    job = completed_job(project, storage)
    storage.fail_copy = True
    with pytest.raises(RuntimeError):
        build_service.request_training_build(job=job, backend="docker", storage=storage)
    assert not Build.objects.exists()
    assert len(storage.deleted) == 1 and "builds" in storage.deleted[0]


def test_project_deletion_during_the_copy_discards_the_build(project, storage):
    job = completed_job(project, storage)
    storage.on_copy = lambda: ModelProject.objects.filter(pk=project.pk).update(deletion_state="deleting")
    with pytest.raises(Conflict):
        build_service.request_training_build(job=job, backend="docker", storage=storage)
    assert not Build.objects.exists()
    assert storage.deleted


def test_changed_training_output_during_the_copy_discards_the_build(project, storage):
    job = completed_job(project, storage)
    storage.on_copy = lambda: TrainingJob.objects.filter(pk=job.pk).update(output_revision=job.output_revision + 1)
    with pytest.raises(Conflict):
        build_service.request_training_build(job=job, backend="docker", storage=storage)
    assert not Build.objects.exists()


def test_a_concurrent_request_that_won_is_reused_and_our_copy_is_dropped(project, storage):
    job = completed_job(project, storage)
    winner = Build.objects.create(
        project=project,
        source_job=job,
        source_job_reference=job.public_id,
        flavor="xgboost",
        status="queued",
        source_output_revision=job.output_revision,
        backend="docker",
    )
    # Not active at the first look, so the request proceeds; active again by the final check.
    Build.objects.filter(pk=winner.pk).update(status="failed")
    storage.on_copy = lambda: Build.objects.filter(pk=winner.pk).update(status="queued")
    build, created = build_service.request_training_build(job=job, backend="docker", storage=storage)
    assert created is False and build.pk == winner.pk
    assert Build.objects.count() == 1
    assert storage.deleted, "the copy made for the losing request must be removed"


def test_failure_after_commit_keeps_the_inputs_of_the_created_build(project, storage):
    """An enqueue failure surfaces after the commit; the Build exists and owns its inputs."""
    job = completed_job(project, storage)
    tasks.execute_build.delay.side_effect = ConnectionError("broker down")
    with pytest.raises(ConnectionError):
        build_service.request_training_build(job=job, backend="docker", storage=storage)
    assert Build.objects.count() == 1
    assert storage.deleted == []


# ---- training jobs -----------------------------------------------------------------------------


@pytest.fixture
def job_storage(monkeypatch, storage):
    monkeypatch.setattr(job_service, "S3Storage", lambda: storage)
    monkeypatch.setattr(job_service.settings, "AWS_STORAGE_BUCKET_NAME", storage.bucket, raising=False)
    return storage


def job_data(**extra):
    return {
        "name": "fresh",
        "model_flavor": "sklearn",
        "entry_point": "train.py",
        "requirements_text": "",
        "source_zip": b"zip-bytes",
        "training_data": SimpleUploadedFile("train.csv", b"a,b\n1,2\n"),
        **extra,
    }


def test_create_job_writes_snapshots_outside_any_transaction(project, job_storage):
    job = job_service.create_job(project=project, validated_data=job_data())
    assert job_storage.inside_transaction == []
    assert TrainingJob.objects.filter(pk=job.pk).exists()
    assert len(job_storage.objects) == 2


def test_create_job_for_a_deleting_project_stores_nothing(project, job_storage):
    ModelProject.objects.filter(pk=project.pk).update(deletion_state="deleting")
    with pytest.raises(Conflict):
        job_service.create_job(project=project, validated_data=job_data())
    assert job_storage.objects == {} and not TrainingJob.objects.exists()


def test_create_job_cleans_up_when_the_project_starts_deleting_mid_upload(project, job_storage):
    original_put = job_storage.put

    def put_then_delete(key, file, content_type="application/octet-stream"):
        result = original_put(key, file, content_type)
        ModelProject.objects.filter(pk=project.pk).update(deletion_state="deleting")
        return result

    job_storage.put = put_then_delete
    with pytest.raises(Conflict):
        job_service.create_job(project=project, validated_data=job_data())
    assert not TrainingJob.objects.exists()
    assert job_storage.deleted


def test_create_job_failure_leaves_no_row_and_cleans_the_prefix(project, job_storage):
    def broken(*args, **kwargs):
        raise RuntimeError("s3 down")

    job_storage.put = broken
    with pytest.raises(RuntimeError):
        job_service.create_job(project=project, validated_data=job_data())
    assert not TrainingJob.objects.exists()
    assert len(job_storage.deleted) == 1


def test_retry_job_copies_inputs_outside_any_transaction(project, job_storage, monkeypatch):
    monkeypatch.setattr(job_service, "submit_job", lambda job: job)
    code = job_storage.put("input/code.zip", b"code")
    failed = TrainingJob.objects.create(
        project=project,
        name="failed",
        model_flavor="sklearn",
        status="failed",
        entry_point="train.py",
        code_snapshot_uri=code.uri,
        data_snapshot_uri=code.uri,
    )
    job_storage.inside_transaction.clear()
    retry = job_service.retry_job(failed, storage=job_storage)
    assert job_storage.inside_transaction == []
    assert retry.retry_of_id == failed.pk and TrainingJob.objects.filter(pk=retry.pk).exists()


# ---- build deletion -----------------------------------------------------------------------------


def deleting_build(project, **extra):
    return Build.objects.create(
        project=project, flavor="sklearn", backend="docker", status="failed", deletion_state="deleting", **extra
    )


@pytest.fixture
def cleanup(monkeypatch):
    """Record whether each external step ran inside a transaction."""
    seen = {}

    def spy(name, result=None):
        def call(*args, **kwargs):
            seen[name] = connection.in_atomic_block
            return result

        return call

    monkeypatch.setattr(tasks, "stop_build_for_deletion", spy("stop"))
    monkeypatch.setattr(tasks, "BuildImageCleaner", lambda: SimpleNamespace(delete=spy("image", "deleted")))
    monkeypatch.setattr(tasks, "S3Storage", lambda: SimpleNamespace(delete_prefix=spy("storage")))
    return seen


def test_delete_build_runs_external_cleanup_outside_any_transaction(project, cleanup):
    build = deleting_build(project)
    assert tasks.delete_build.run(str(build.public_id)) == "deleted"
    assert cleanup == {"stop": False, "image": False, "storage": False}
    assert not Build.objects.filter(pk=build.pk).exists()


def test_delete_build_keeps_a_build_that_was_registered_during_cleanup(project, monkeypatch):
    build = deleting_build(project)
    monkeypatch.setattr(tasks, "stop_build_for_deletion", Mock())
    monkeypatch.setattr(tasks, "S3Storage", lambda: SimpleNamespace(delete_prefix=Mock()))

    def registers_meanwhile(*args, **kwargs):
        Build.objects.filter(pk=build.pk).update(registration_status="registering")
        return "deleted"

    monkeypatch.setattr(tasks, "BuildImageCleaner", lambda: SimpleNamespace(delete=registers_meanwhile))
    retry = Mock(side_effect=Exception("retry"))
    monkeypatch.setattr(tasks.delete_build, "retry", retry)
    with pytest.raises(Exception, match="retry"):
        tasks.delete_build.run(str(build.public_id))
    assert Build.objects.filter(pk=build.pk).exists()


def test_delete_build_failure_is_recorded_and_retried(project, monkeypatch):
    build = deleting_build(project)
    monkeypatch.setattr(tasks, "stop_build_for_deletion", Mock(side_effect=RuntimeError("runner still active")))
    monkeypatch.setattr(tasks.delete_build, "retry", Mock(side_effect=Exception("retry")))
    with pytest.raises(Exception, match="retry"):
        tasks.delete_build.run(str(build.public_id))
    build.refresh_from_db()
    assert build.deletion_state == "delete_failed"


# ---- stalled deletions --------------------------------------------------------------------------


def age(model, pk, field="updated_at", minutes=60):
    model.objects.filter(pk=pk).update(**{field: timezone.now() - timedelta(minutes=minutes)})


@pytest.fixture
def dispatch(monkeypatch, settings):
    from django.core.cache import cache

    cache.clear()
    settings.DELETION_RECONCILE_GRACE_SECONDS = 600
    mocks = SimpleNamespace(build=Mock(), project=Mock(), job=Mock())
    monkeypatch.setattr(tasks.delete_build, "delay", mocks.build)
    monkeypatch.setattr(catalog_tasks.execute_project_deletion, "delay", mocks.project)
    monkeypatch.setattr(training_tasks.delete_training_job, "delay", mocks.job)
    return mocks


def test_stalled_deletions_are_dispatched_again(project, dispatch):
    stale = deleting_build(project)
    fresh = deleting_build(project)
    failed = Build.objects.create(project=project, flavor="sklearn", backend="docker", deletion_state="delete_failed")
    active = Build.objects.create(project=project, flavor="sklearn", backend="docker")
    for build in (stale, failed, active):
        age(Build, build.pk)
    other_owner = get_user_model().objects.create_user("p2@example.com", "test-password")
    stale_project = ModelProject.objects.create(owner=other_owner, name="gone", deletion_state="deleting")
    age(ModelProject, stale_project.pk)
    job = TrainingJob.objects.create(
        project=project, name="j", model_flavor="sklearn", status="cancelled", deletion_requested_at=timezone.now()
    )
    TrainingJob.objects.filter(pk=job.pk).update(deletion_requested_at=timezone.now() - timedelta(hours=1))
    errored = TrainingJob.objects.create(
        project=project,
        name="e",
        model_flavor="sklearn",
        status="cancelled",
        deletion_requested_at=timezone.now() - timedelta(hours=1),
        deletion_error="blocked",
    )

    assert tasks.reconcile_stalled_deletions() == 3
    dispatch.build.assert_called_once_with(str(stale.public_id))
    dispatch.project.assert_called_once_with(str(stale_project.public_id))
    dispatch.job.assert_called_once_with(str(job.public_id))
    assert str(fresh.public_id) not in str(dispatch.build.call_args_list)
    assert str(errored.public_id) not in str(dispatch.job.call_args_list)

    # A deletion that keeps failing is not re-enqueued on every scan.
    assert tasks.reconcile_stalled_deletions() == 0


def test_beat_runs_the_deletion_reconciler(settings):
    from config.settings import base

    entry = base.CELERY_BEAT_SCHEDULE["stalled-deletion-reconcile"]
    assert entry["task"] == "apps.deployment.tasks.reconcile_stalled_deletions"
    assert entry["schedule"] == base.DELETION_RECONCILE_INTERVAL_SECONDS


@pytest.mark.parametrize(
    "task",
    [
        tasks.delete_build,
        tasks.cancel_build,
        tasks.cleanup_failed_build_artifacts,
        tasks.stop_deployment,
        catalog_tasks.execute_project_deletion,
        catalog_tasks.complete_project_deletion,
        training_tasks.delete_training_job,
        training_tasks.purge_training_job_outputs,
    ],
)
def test_cleanup_tasks_are_redelivered_when_their_worker_dies(task):
    """acks_late alone acknowledges the message of a killed worker; the task would be lost."""
    assert task.acks_late is True
    assert task.reject_on_worker_lost is True
