import uuid
from datetime import timedelta
from io import BytesIO
from unittest.mock import Mock

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.training.models import TrainingQuotaReservation
from apps.training.services import drafts
from apps.training.services.preparation import PreparationStorage, prepare_training_input
from common.api.exceptions import Conflict

from .test_job_drafts import studio as studio

pytestmark = pytest.mark.django_db


def pending(workspace):
    return drafts.run_workspace(workspace, revision=workspace.revision, run_key=uuid.uuid4())


def test_run_returns_202_without_storage_or_reservation(studio, monkeypatch, django_capture_on_commit_callbacks):
    workspace, storage, client, _ = studio
    storage.read = Mock(side_effect=AssertionError("HTTP must not read Input"))
    probe = Mock(side_effect=AssertionError("HTTP must not probe Docker"))
    monkeypatch.setattr("apps.training.services.local_resources.require_capacity", probe)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = client.post(
            f"/api/training-workspaces/{workspace.public_id}/runs/",
            {"revision": workspace.revision, "run_key": str(uuid.uuid4())}, format="json",
        )
        drafts.enqueue_preparation.assert_not_called()
    assert len(callbacks) == 1
    drafts.enqueue_preparation.assert_called_once()
    assert response.status_code == 202 and response.data["status"] == "pending"
    assert not TrainingQuotaReservation.objects.exists()
    storage.read.assert_not_called()
    assert workspace.status == "preparing"


def test_preparation_claim_and_delivery_replay(studio):
    workspace, storage, _, enqueue = studio
    job = pending(workspace)
    token = job.submission_token
    result = drafts.prepare_workspace(job.public_id, token, storage=storage)
    assert result.status == "queued" and result.submitted_at
    assert result.submission_token != token
    assert drafts.prepare_workspace(job.public_id, token, storage=storage) is None
    assert TrainingQuotaReservation.objects.count() == 1
    enqueue.assert_not_called()  # execution is also dispatched only on commit


def test_expired_queue_item_never_downloads(studio):
    workspace, storage, _, _ = studio
    job = pending(workspace)
    job.preparation_started_at = timezone.now() - timedelta(minutes=11)
    job.save(update_fields=["preparation_started_at"])
    storage.read = Mock()
    assert drafts.prepare_workspace(job.public_id, job.submission_token, storage=storage) is None
    job.refresh_from_db()
    assert job.status == "failed" and workspace.status == "ready"
    storage.read.assert_not_called()


def test_publish_failure_fails_pending_job_without_quota(studio, monkeypatch):
    workspace, _, _, _ = studio
    job = pending(workspace)
    monkeypatch.setattr(prepare_training_input, "apply_async", Mock(side_effect=OSError("broker down")))
    publish(job.public_id, job.submission_token)
    job.refresh_from_db()
    assert job.status == "failed" and not job.submission_token
    assert not TrainingQuotaReservation.objects.exists()


publish = drafts.enqueue_preparation


def test_checksum_failure_does_not_publish_snapshot(studio):
    workspace, storage, _, _ = studio
    job = pending(workspace)
    storage.read = Mock(return_value=b"corrupt")
    with pytest.raises(ValidationError):
        drafts.prepare_workspace(job.public_id, job.submission_token, storage=storage)
    job.refresh_from_db()
    assert job.status == "failed" and not job.submitted_at and not job.code_snapshot_uri
    assert not TrainingQuotaReservation.objects.exists()


def test_deletion_during_upload_fences_admission(studio):
    workspace, storage, _, _ = studio
    job = pending(workspace)
    put = storage.put
    def cancel_during_put(*args):
        result = put(*args)
        type(job).objects.filter(pk=job.pk).update(status="cancelled", submission_token=None)
        return result
    storage.put = cancel_during_put
    with pytest.raises(Conflict):
        drafts.prepare_workspace(job.public_id, job.submission_token, storage=storage)
    job.refresh_from_db()
    assert job.status == "cancelled" and not job.submitted_at
    assert storage.deleted and not TrainingQuotaReservation.objects.exists()


def test_worker_loss_is_recovered_without_second_claim(studio):
    workspace, storage, _, _ = studio
    job = pending(workspace)
    token = job.submission_token
    storage.read = Mock(side_effect=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        drafts.prepare_workspace(job.public_id, token, storage=storage)
    assert drafts.prepare_workspace(job.public_id, token, storage=storage) is None
    type(job).objects.filter(pk=job.pk).update(preparation_started_at=timezone.now() - timedelta(minutes=11))
    assert drafts.recover_preparations() == 1
    assert workspace.status == "ready"
    assert not TrainingQuotaReservation.objects.exists()


@pytest.mark.parametrize("payload,limit,failed", [(b"abc", 3, False), (b"abcd", 3, True)])
def test_chunked_reads_are_bounded_and_close_stream(payload, limit, failed):
    storage = object.__new__(PreparationStorage)
    storage.checkpoint = Mock()
    body = BytesIO(payload)
    storage.open_stream = Mock(return_value=(body, len(payload), "text/plain"))
    if failed:
        with pytest.raises(ValueError):
            storage.read("unused", limit)
    else:
        assert storage.read("unused", limit) == payload
    assert body.closed
