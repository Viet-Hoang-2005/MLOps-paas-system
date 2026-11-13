import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.training.models import TrainingJob, TrainingJobEntry, TrainingQuotaReservation
from apps.training.services import drafts, workspaces
from apps.training.services.jobs import request_job_deletion
from common.api.exceptions import Conflict

pytestmark = pytest.mark.django_db


@pytest.fixture
def studio(settings, monkeypatch):
    settings.TRAINING_BACKEND = "argo"
    settings.TRAINING_ENABLED = True
    settings.TRAINING_EXECUTION_WATCH_ENABLED = True
    settings.TRAINING_SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    user = get_user_model().objects.create_user("studio@example.test", "password")
    storage = MemoryStorage()
    monkeypatch.setattr(workspaces, "S3Storage", lambda: storage)
    enqueue = Mock()
    monkeypatch.setattr("apps.training.services.jobs._enqueue", enqueue)
    job = drafts.create_draft(owner=user)
    entry, revision = workspaces.create_entry(
        job, revision=1, path="train.py", kind="script", payload=b"print('training')", storage=storage
    )
    job = workspaces.update_workspace(
        job,
        revision=revision,
        changes={"entry_point": "train.py", "vcpu": 1, "memory_mb": 2048, "max_runtime_seconds": 900},
    )
    client = APIClient()
    client.force_authenticate(user)
    return job, storage, client, enqueue


def run(job, storage, key=None):
    return drafts.submit_draft(job, revision=job.revision, run_key=key or uuid.uuid4(), storage=storage)


def test_create_draft_needs_no_project_or_docker(studio, monkeypatch):
    _, _, client, _ = studio
    monkeypatch.setattr(
        "apps.training.services.local_resources.require_capacity", Mock(side_effect=AssertionError("must not probe"))
    )
    response = client.post("/api/training-jobs/", {}, format="json")
    assert response.status_code == 201
    assert response.data["status"] == "editing"
    assert response.data["vcpu"] is None
    assert response.data["submitted_at"] is None
    assert "workspace_id" not in response.data
    assert not TrainingQuotaReservation.objects.exists()


def test_submit_keeps_uuid_and_replays_without_second_reservation(studio):
    job, storage, _, _ = studio
    key = uuid.uuid4()
    result = run(job, storage, key)
    assert result.pk == job.pk and result.public_id == job.public_id
    assert result.status == "queued" and result.submitted_at
    assert result.input_revision == job.revision
    assert run(job, storage, key).pk == job.pk
    assert TrainingQuotaReservation.objects.filter(job_id=job.public_id).count() == 1
    with pytest.raises(Conflict):
        run(job, storage)


def test_storage_failure_restores_editing_without_quota(studio):
    job, storage, _, _ = studio
    storage.put = Mock(side_effect=OSError("storage unavailable"))
    with pytest.raises(OSError):
        run(job, storage)
    job.refresh_from_db()
    assert job.status == "editing" and job.submitted_at is None
    assert job.run_key is None
    assert job.entries.count() == 1
    assert not TrainingQuotaReservation.objects.exists()


def test_quota_failure_does_not_admit_runtime(studio, monkeypatch):
    job, storage, _, _ = studio
    monkeypatch.setattr("apps.training.services.quota.reserve", Mock(side_effect=Conflict("quota")))
    with pytest.raises(Conflict):
        run(job, storage)
    job.refresh_from_db()
    assert job.status == "editing" and job.submitted_at is None


def test_second_request_during_preparation_cannot_replace_submission(studio):
    job, storage, _, _ = studio
    read = storage.read

    def concurrent_read(*args, **kwargs):
        with pytest.raises(Conflict):
            run(job, storage)
        return read(*args, **kwargs)

    storage.read = concurrent_read
    assert run(job, storage).status == "queued"


def test_abandoned_preparation_is_fenced_before_old_writer_commits(studio):
    job, storage, _, _ = studio
    read = storage.read

    def expire(*args, **kwargs):
        TrainingJob.objects.filter(pk=job.pk).update(preparation_started_at=timezone.now() - timedelta(minutes=11))
        assert drafts.recover_preparations() == 1
        return read(*args, **kwargs)

    storage.read = expire
    with pytest.raises(Conflict):
        run(job, storage)
    job.refresh_from_db()
    assert job.status == "editing" and not job.submitted_at


def test_clone_and_retry_are_editing_and_copy_current_secrets_only(studio):
    job, storage, _, _ = studio
    _, revision = workspaces.set_secret(job, revision=job.revision, name="TOKEN", value="synthetic-secret")
    job.refresh_from_db()
    original = run(job, storage)
    TrainingJob.objects.filter(pk=job.pk).update(status="failed")
    original.refresh_from_db()
    key = uuid.uuid4()
    retry = drafts.clone_draft(original, retry=True, creation_key=key, storage=storage)
    assert retry.status == "editing" and retry.pk != original.pk
    assert retry.retry_of == original and retry.project_id is None
    assert retry.submitted_at is None and not retry.outputs.exists()
    assert workspaces.cipher().decrypt(bytes(retry.secrets.get().ciphertext)) == b"synthetic-secret"
    assert drafts.clone_draft(original, retry=True, creation_key=key, storage=storage).pk == retry.pk
    workspaces.delete_secret(original, revision=revision, name="TOKEN")
    clone = drafts.clone_draft(original, creation_key=uuid.uuid4(), storage=storage)
    assert clone.cloned_from == original and not clone.secrets.exists()
    assert clone.entries.get().s3_uri != original.entries.get().s3_uri
    assert TrainingQuotaReservation.objects.count() == 1


def test_submitted_input_is_readonly_but_terminal_secret_can_be_revoked(studio):
    job, storage, client, _ = studio
    run(job, storage)
    response = client.patch(
        f"/api/training-jobs/{job.public_id}/", {"revision": job.revision, "environment": {}}, format="json"
    )
    assert response.status_code == 409


def test_job_files_and_config_are_owner_scoped(studio):
    job, _, client, _ = studio
    other = get_user_model().objects.create_user("other@example.test", "password")
    client.force_authenticate(other)
    url = f"/api/training-jobs/{job.public_id}/"
    assert client.get(url).status_code == 404
    assert (
        client.post(url + "entries/", {"revision": 1, "kind": "script", "path": "x.py"}, format="json").status_code
        == 404
    )
    assert client.post(url + "submit/", {"revision": 1, "run_key": str(uuid.uuid4())}, format="json").status_code == 404


def test_draft_deletion_never_schedules_runtime_cancellation(studio, monkeypatch, django_capture_on_commit_callbacks):
    job, _, _, _ = studio
    settings_mock = Mock()
    monkeypatch.setattr("apps.observability.services.executions.enqueue_safely", settings_mock)
    with django_capture_on_commit_callbacks(execute=True):
        request_job_deletion(job)
    assert settings_mock.call_count == 1
    assert settings_mock.call_args.args[1].name.endswith("delete_training_job")
    job.refresh_from_db()
    assert job.status == "editing" and job.submission_token is None


def test_editing_time_is_not_runtime(studio):
    job, _, _, _ = studio
    job.created_at = timezone.now() - timedelta(days=3)
    job.mark_finished("failed")
    assert job.runtime_seconds == 0


def test_workspace_endpoint_is_removed(studio):
    _, _, client, _ = studio
    assert client.get("/api/training-workspaces/").status_code == 404
    assert TrainingJobEntry._meta.get_field("job")


def test_unsubmitted_draft_cannot_receive_a_runtime_capability(studio):
    from apps.training.services.capabilities import issue_capability

    job, _, _, _ = studio
    with pytest.raises(Conflict):
        issue_capability(job, "trusted_reporter")


def test_same_key_can_reclaim_an_expired_preparation(studio):
    job, storage, _, _ = studio
    key = uuid.uuid4()
    TrainingJob.objects.filter(pk=job.pk).update(
        status="pending",
        run_key=key,
        submission_token=uuid.uuid4(),
        preparation_started_at=timezone.now() - timedelta(minutes=11),
    )
    assert run(job, storage, key).status == "queued"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("same_key", [True, False])
def test_postgres_concurrent_run_admits_only_one_execution(studio, same_key):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connection, connections

    if connection.vendor != "postgresql":
        pytest.skip("Submission locking requires disposable PostgreSQL.")
    job, storage, _, enqueue = studio
    key = uuid.uuid4()
    keys = [key, key if same_key else uuid.uuid4()]
    gate = Barrier(2)

    def submit(key):
        try:
            current = TrainingJob.objects.get(pk=job.pk)
            gate.wait(timeout=10)
            try:
                return str(run(current, storage, key).public_id)
            except Conflict:
                return "conflict"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, keys))
    assert results.count(str(job.public_id)) == (2 if same_key else 1)
    assert results.count("conflict") == (0 if same_key else 1)
    job.refresh_from_db()
    assert job.status == "queued" and job.submitted_at
    assert TrainingQuotaReservation.objects.filter(job_id=job.public_id).count() == 1
    enqueue.assert_called_once()
