from unittest.mock import Mock

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob, TrainingJobCapability, TrainingOutput
from apps.training.services.capabilities import issue_capability
from apps.training.services.storage_scope import expected_training_uris


def _job(email="owner@example.com"):
    user = get_user_model().objects.create_user(email, "password123")
    project = ModelProject.objects.create(owner=user, name=f"project-{email}")
    job = TrainingJob.objects.create(
        project=project,
        name="nightly",
        model_flavor="sklearn",
        code_snapshot_uri="pending",
        data_snapshot_uri="pending",
        output_uri="pending",
        status="running",
    )
    uris = expected_training_uris(job, settings.AWS_STORAGE_BUCKET_NAME)
    job.code_snapshot_uri = uris["code"]
    job.data_snapshot_uri = uris["data"]
    job.output_uri = uris["output"]
    job.mlflow_artifact_uri = uris["mlflow"]
    job.save(update_fields=["code_snapshot_uri", "data_snapshot_uri", "output_uri", "mlflow_artifact_uri"])
    return job


@pytest.mark.django_db
def test_capability_is_hashed_and_bound_to_job_and_purpose():
    first = _job("first@example.com")
    second = _job("second@example.com")
    token = issue_capability(first, "output_upload")

    capability = TrainingJobCapability.objects.get(job=first)
    assert capability.token_hash != token
    assert token not in capability.token_hash

    response = APIClient().post(
        f"/internal/training-jobs/{second.public_id}/output-upload-url/",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_output_upload_capability_is_one_time_and_put_scoped(monkeypatch):
    job = _job()
    token = issue_capability(job, "output_upload")
    storage = Mock()
    storage.bucket = settings.AWS_STORAGE_BUCKET_NAME
    storage.presigned_put.return_value = "https://s3.example/job-output"
    monkeypatch.setattr("apps.training.api.webhooks.S3Storage", lambda: storage)
    client = APIClient()
    url = f"/internal/training-jobs/{job.public_id}/output-upload-url/"

    response = client.post(url, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
    storage.presigned_put.assert_called_once_with(
        job.output_uri,
        settings.TRAINING_PRESIGNED_URL_TTL_SECONDS,
        "application/gzip",
    )
    assert TrainingJobCapability.objects.get(job=job).consumed_at is not None
    assert client.post(url, HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 403


@pytest.mark.django_db
def test_expired_capability_and_legacy_shared_secret_are_rejected():
    job = _job()
    token = issue_capability(job, "output_upload")
    TrainingJobCapability.objects.filter(job=job).update(expires_at=timezone.now())
    client = APIClient()

    assert (
        client.post(
            f"/internal/training-jobs/{job.public_id}/output-upload-url/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/internal/webhooks/training-jobs/{job.public_id}/",
            {"workflow_status": "Succeeded"},
            format="json",
            HTTP_X_CONTROL_PLANE_SECRET="legacy-shared-secret",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_trusted_reporter_sets_terminal_status_once():
    job = _job()
    token = issue_capability(job, "trusted_reporter")
    client = APIClient()
    url = f"/internal/webhooks/training-jobs/{job.public_id}/"
    headers = {
        "HTTP_AUTHORIZATION": f"Bearer {token}",
        "HTTP_IDEMPOTENCY_KEY": "workflow-1",
    }

    response = client.post(url, {"workflow_status": "Succeeded"}, format="json", **headers)
    assert response.status_code == 200
    job.refresh_from_db()
    assert job.status == "completed"
    assert TrainingOutput.objects.filter(job=job, relative_path="model.tar.gz").exists()

    duplicate = client.post(url, {"workflow_status": "Succeeded"}, format="json", **headers)
    assert duplicate.status_code == 200
    assert duplicate.data["duplicate"] is True


@pytest.mark.django_db
def test_trusted_reporter_cannot_overwrite_cancelled_job():
    job = _job()
    job.mark_finished("cancelled")
    job.save(update_fields=["status", "completed_at", "runtime_seconds", "updated_at"])
    token = issue_capability(job, "trusted_reporter")

    response = APIClient().post(
        f"/internal/webhooks/training-jobs/{job.public_id}/",
        {"workflow_status": "Succeeded"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    assert response.status_code == 200
    job.refresh_from_db()
    assert job.status == "cancelled"
    assert response.data["ignored"] is True


@pytest.mark.django_db
def test_cancel_reporter_is_job_bound_one_time_and_confirms_cancellation():
    job = _job()
    job.status = "cancelling"
    job.save(update_fields=["status", "updated_at"])
    token = issue_capability(job, "cancel_reporter", ttl_seconds=600)
    client = APIClient()
    url = f"/internal/webhooks/training-jobs/{job.public_id}/cancellation/"
    headers = {
        "HTTP_AUTHORIZATION": f"Bearer {token}",
        "HTTP_IDEMPOTENCY_KEY": "cancel-workflow-1",
    }

    response = client.post(
        url,
        {"workflow_status": "Succeeded"},
        format="json",
        **headers,
    )

    assert response.status_code == 200
    job.refresh_from_db()
    assert job.status == "cancelled"
    duplicate = client.post(
        url,
        {"workflow_status": "Succeeded"},
        format="json",
        **headers,
    )
    assert duplicate.status_code == 200
    assert duplicate.data["duplicate"] is True


@pytest.mark.django_db
def test_late_callbacks_are_ignored_after_training_job_is_deleted():
    job = _job()
    job_id = job.public_id
    job.delete()
    client = APIClient()

    training_response = client.post(
        f"/internal/webhooks/training-jobs/{job_id}/",
        {"workflow_status": "Succeeded"},
        format="json",
    )
    cancellation_response = client.post(
        f"/internal/webhooks/training-jobs/{job_id}/cancellation/",
        {"workflow_status": "Succeeded"},
        format="json",
    )

    assert training_response.status_code == 200
    assert training_response.data == {"status": "deleted", "ignored": True}
    assert cancellation_response.status_code == 200
    assert cancellation_response.data == {"status": "deleted", "duplicate": True}
