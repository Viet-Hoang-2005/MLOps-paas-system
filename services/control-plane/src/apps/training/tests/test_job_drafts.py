import uuid
from datetime import timedelta
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.training.models import TrainingJob, TrainingWorkspace, TrainingQuotaReservation
from apps.training.services import drafts, workspaces
from common.api.exceptions import Conflict

pytestmark = pytest.mark.django_db


@pytest.fixture
def studio(settings, monkeypatch):
    monkeypatch.setattr(drafts, "enqueue_preparation", Mock())
    settings.TRAINING_BACKEND = "argo"
    settings.TRAINING_ENABLED = True
    settings.TRAINING_EXECUTION_WATCH_ENABLED = True
    settings.TRAINING_SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    user = get_user_model().objects.create_user("studio@example.test", "password")
    storage = MemoryStorage()
    monkeypatch.setattr(workspaces, "S3Storage", lambda: storage)
    enqueue = Mock()
    monkeypatch.setattr("apps.training.services.jobs._enqueue", enqueue)
    workspace = drafts.create_workspace(owner=user)
    _, revision = workspaces.create_entry(
        workspace, revision=1, path="train.py", kind="script", payload=b"print('training')", storage=storage
    )
    workspace = workspaces.update_workspace(
        workspace,
        revision=revision,
        changes={"entry_point": "train.py", "vcpu": 1, "memory_mb": 2048, "max_runtime_seconds": 900},
    )
    client = APIClient()
    client.force_authenticate(user)
    return workspace, storage, client, enqueue


def run(workspace, storage, key=None):
    job = drafts.run_workspace(workspace, revision=workspace.revision, run_key=key or uuid.uuid4())
    return drafts.prepare_workspace(job.public_id, job.submission_token, storage=storage) or job


def finish(job):
    job.status = "failed"
    job.save(update_fields=["status"])
    TrainingQuotaReservation.objects.filter(job_id=job.public_id).update(active=False)


def test_create_workspace_needs_no_project_or_docker(studio, monkeypatch):
    _, _, client, _ = studio
    monkeypatch.setattr(
        "apps.training.services.local_resources.require_capacity", Mock(side_effect=AssertionError("must not probe"))
    )
    response = client.post("/api/training-workspaces/", {}, format="json")
    assert response.status_code == 201
    assert response.data["status"] == "ready" and response.data["vcpu"] is None
    assert not TrainingJob.objects.exists() and not TrainingQuotaReservation.objects.exists()


def test_run_creates_new_identity_and_replays_once(studio):
    workspace, storage, _, _ = studio
    key = uuid.uuid4()
    result = run(workspace, storage, key)
    assert result.public_id != workspace.public_id and result.workspace_id == workspace.pk
    assert result.status == "queued" and result.submitted_at
    assert result.input_revision == workspace.revision
    assert run(workspace, storage, key).pk == result.pk
    assert TrainingQuotaReservation.objects.filter(job_id=result.public_id).count() == 1
    with pytest.raises(Conflict):
        run(workspace, storage)


def test_two_runs_preserve_old_input_and_current_secrets(studio):
    workspace, storage, _, _ = studio
    _, revision = workspaces.set_secret(workspace, revision=workspace.revision, name="TOKEN", value="first")
    workspace.refresh_from_db()
    first = run(workspace, storage)
    original = storage.objects[first.code_snapshot_uri]
    finish(first)
    workspaces.delete_secret(workspace, revision=revision, name="TOKEN")
    workspace.refresh_from_db()
    entry = workspace.entries.get(relative_path="train.py")
    _, revision = workspaces.edit_file(
        workspace, entry.public_id, revision=workspace.revision, payload=b"print('second')", storage=storage
    )
    workspace.refresh_from_db()
    second = run(workspace, storage)
    assert first.pk != second.pk and workspace.jobs.count() == 2
    assert storage.objects[first.code_snapshot_uri] == original
    with ZipFile(BytesIO(storage.objects[second.code_snapshot_uri])) as archive:
        assert archive.read("train.py") == b"print('second')"
    assert first.secret_snapshot and not second.secret_snapshot


def test_active_and_cleanup_pending_lock_mutations(studio):
    workspace, storage, _, _ = studio
    job = run(workspace, storage)
    with pytest.raises(Conflict):
        workspaces.update_workspace(workspace, revision=workspace.revision, changes={"environment": {"X": "1"}})
    finish(job)
    job.observation_status = "cleanup_pending"
    job.save(update_fields=["observation_status"])
    with pytest.raises(Conflict):
        run(workspace, storage)
    assert TrainingJob.objects.count() == 1


def test_storage_failure_keeps_draft_without_quota(studio):
    workspace, storage, _, _ = studio
    storage.put = Mock(side_effect=OSError("storage unavailable"))
    with pytest.raises(OSError):
        run(workspace, storage)
    workspace.refresh_from_db()
    assert workspace.status == "ready" and workspace.entries.count() == 1
    assert workspace.jobs.get().status == "failed"
    assert not TrainingQuotaReservation.objects.exists()


def test_broker_failure_does_not_restore_editing(studio, monkeypatch, django_capture_on_commit_callbacks):
    workspace, storage, _, _ = studio
    monkeypatch.setattr("apps.training.services.jobs._enqueue", Mock(side_effect=OSError("broker unavailable")))
    with pytest.raises(OSError), django_capture_on_commit_callbacks(execute=True):
        run(workspace, storage)
    assert workspace.jobs.get().submitted_at is not None


def test_recovery_fences_expired_preparation(studio):
    workspace, _, _, _ = studio
    job = TrainingJob.objects.create(
        workspace=workspace,
        owner=workspace.owner,
        status="pending",
        run_key=uuid.uuid4(),
        submission_token=uuid.uuid4(),
        preparation_started_at=timezone.now() - timedelta(minutes=11),
    )
    assert drafts.recover_preparations() == 1
    job.refresh_from_db()
    assert job.status == "failed" and job.submission_token is None and workspace.status == "ready"


def test_api_nested_identity_and_legacy_mutations_removed(studio):
    workspace, storage, client, _ = studio
    response = client.post(
        f"/api/training-workspaces/{workspace.public_id}/runs/",
        {"revision": workspace.revision, "run_key": str(uuid.uuid4())},
        format="json",
    )
    assert response.status_code == 202
    assert response.data["status"] == "pending"
    job_id = response.data["id"]
    nested = f"/api/training-workspaces/{workspace.public_id}/jobs/{job_id}/"
    assert client.get(nested).status_code == 200
    other = drafts.create_workspace(owner=workspace.owner)
    assert client.get(f"/api/training-workspaces/{other.public_id}/jobs/{job_id}/").status_code == 404
    assert client.patch(f"/api/training-jobs/{job_id}/", {}, format="json").status_code == 405
    assert client.post("/api/training-jobs/", {}, format="json").status_code == 405
    for action in ["submit", "retry", "clone"]:
        assert client.post(f"/api/training-jobs/{job_id}/{action}/", {}, format="json").status_code == 404
    assert "secret_snapshot" not in client.get(nested).data


def test_revision_or_validation_errors_create_no_jobs(studio):
    workspace, storage, _, _ = studio
    with pytest.raises(Conflict):
        drafts.run_workspace(workspace, revision=workspace.revision + 1, run_key=uuid.uuid4())
    workspace.entry_point = ""
    workspace.save(update_fields=["entry_point"])
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        run(workspace, storage)
    assert not TrainingJob.objects.exists()


def test_workspace_list_has_counts_and_tenant_scope(studio):
    workspace, storage, client, _ = studio
    run(workspace, storage)
    data = client.get("/api/training-workspaces/").data["workspaces"]
    assert data[0]["job_count"] == 1 and data[0]["status"] == "running"
    assert "name" not in data[0]
    client.force_authenticate(get_user_model().objects.create_user("other@example.test"))
    assert client.get("/api/training-workspaces/").data["workspaces"] == []
    assert client.get(f"/api/training-workspaces/{workspace.public_id}/").status_code == 404
    assert TrainingWorkspace.objects.count() == 1


def test_workspace_list_aggregates_without_per_workspace_queries(studio, django_assert_num_queries):
    workspace, _, client, _ = studio
    for _ in range(4):
        drafts.create_workspace(owner=workspace.owner)
    with django_assert_num_queries(2):
        response = client.get("/api/training-workspaces/")
    assert len(response.data["workspaces"]) == 5
