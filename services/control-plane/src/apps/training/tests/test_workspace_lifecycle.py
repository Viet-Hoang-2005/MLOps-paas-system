from unittest.mock import Mock

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import ModelProject
from apps.deployment.models import Build
from apps.training.models import TrainingJob, TrainingQuotaReservation
from apps.training.services import drafts
from apps.training.services.workspace_lifecycle import cleanup_workspace, request_workspace_deletion
from common.api.exceptions import Conflict

from .test_job_drafts import studio as studio
from .test_job_drafts import run

pytestmark = pytest.mark.django_db


def test_workspace_deletion_waits_for_jobs_and_keeps_input_until_cleanup(studio, monkeypatch):
    workspace, storage, _, _ = studio
    job = run(workspace, storage)
    monkeypatch.setattr("apps.training.services.jobs.cancel_training_job.delay", Mock())
    monkeypatch.setattr(cleanup_workspace, "delay", Mock())
    request_workspace_deletion(workspace)
    workspace.refresh_from_db()
    job.refresh_from_db()
    assert workspace.status == "deleting" and job.status == "cancelling"
    assert workspace.entries.exists() and storage.objects
    with pytest.raises(Conflict):
        run(workspace, storage)


def test_workspace_deletion_rejects_build_references_atomically(studio):
    workspace, storage, _, _ = studio
    job = run(workspace, storage)
    project = ModelProject.objects.create(owner=workspace.owner, name="Blocking project")
    Build.objects.create(project=project, source_job=job, status="ready", flavor="sklearn")
    with pytest.raises(Conflict):
        request_workspace_deletion(workspace)
    workspace.refresh_from_db()
    job.refresh_from_db()
    assert workspace.deletion_requested_at is None and job.deletion_requested_at is None


def test_cleanup_failure_is_retryable_without_deleting_workspace(studio, monkeypatch):
    workspace, _, _, _ = studio
    workspace.deletion_requested_at = timezone.now()
    workspace.save()
    storage = Mock()
    storage.delete_prefix.side_effect = OSError("storage offline")
    monkeypatch.setattr("apps.training.services.workspace_lifecycle.S3Storage", lambda: storage)
    with pytest.raises(OSError):
        cleanup_workspace.run(str(workspace.public_id))
    workspace.refresh_from_db()
    assert workspace.status == "delete_failed" and workspace.entries.exists()
    storage.delete_prefix.side_effect = None
    cleanup_workspace.run(str(workspace.public_id))
    assert not type(workspace).objects.filter(pk=workspace.pk).exists()


def test_database_prevents_second_active_job(studio):
    workspace, storage, _, _ = studio
    run(workspace, storage)
    with pytest.raises(IntegrityError), transaction.atomic():
        TrainingJob.objects.create(workspace=workspace, owner=workspace.owner, status="pending")


def test_terminal_job_with_reservation_still_locks_workspace(studio):
    workspace, storage, _, _ = studio
    job = run(workspace, storage)
    TrainingJob.objects.filter(pk=job.pk).update(status="completed")
    assert workspace.status == "running"
    with pytest.raises(Conflict):
        run(workspace, storage)
    TrainingQuotaReservation.objects.filter(job_id=job.public_id).update(active=False)
    assert workspace.status == "ready"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("replay", [False, True])
def test_concurrent_run_is_serialized_by_workspace(studio, replay):
    import uuid
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connection, connections

    if connection.vendor != "postgresql":
        pytest.skip("Workspace row-lock concurrency requires disposable PostgreSQL.")
    workspace, storage, _, _ = studio
    gate = Barrier(2)
    first = uuid.uuid4()

    def submit(key):
        try:
            gate.wait(timeout=10)
            try:
                return drafts.run_workspace(workspace, revision=workspace.revision, run_key=key, storage=storage).pk
            except Conflict:
                return None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [first, first if replay else uuid.uuid4()]))
    assert workspace.jobs.count() == 1
    assert len({value for value in results if value is not None}) == 1
    assert sum(value is not None for value in results) == (2 if replay else 1)
