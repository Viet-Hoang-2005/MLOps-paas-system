import pytest
from django.contrib.auth import get_user_model
from infrastructure.execution.argo_backends import ArgoTrainingBackend

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob
from apps.training.services.storage_scope import expected_training_uris


class FakeArgoClient:
    def __init__(self):
        self.calls = []

    def trigger(self, url, payload):
        self.calls.append((url, payload))
        return {"accepted": True}


class FakeStorage:
    bucket = "bucket"

    def presigned_get(self, uri, expires_in):
        return f"https://storage.example/download?uri={uri}&expires={expires_in}"

    def presigned_put(self, uri, expires_in):
        return f"https://storage.example/upload?uri={uri}&expires={expires_in}"


@pytest.mark.django_db
def test_argo_training_backend_records_runtime_selectors():
    user = get_user_model().objects.create_user("owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="NIDS")
    job = TrainingJob.objects.create(
        project=project,
        name="nightly",
        code_snapshot_uri="s3://bucket/code.zip",
        data_snapshot_uri="s3://bucket/train.csv",
        output_uri="s3://bucket/model.tar.gz",
        mlflow_artifact_uri="s3://bucket/mlflow/",
    )
    scoped_uris = expected_training_uris(job, "bucket")
    job.code_snapshot_uri = scoped_uris["code"]
    job.data_snapshot_uri = scoped_uris["data"]
    job.output_uri = scoped_uris["output"]
    job.mlflow_artifact_uri = scoped_uris["mlflow"]
    job.save(update_fields=["code_snapshot_uri", "data_snapshot_uri", "output_uri", "mlflow_artifact_uri"])
    client = FakeArgoClient()

    ArgoTrainingBackend(client=client, storage=FakeStorage()).run(job)

    job.refresh_from_db()
    runtime_name = f"training-{job.public_id}"
    expected_selector = f"mlops.io/training-job-id={job.public_id}"
    assert job.external_job_id == runtime_name
    assert job.tracking["runtime"] == {
        "backend": "argo",
        "namespace": "user-jobs",
        "pytorch_job_name": runtime_name,
        "workflow_selector": expected_selector,
        "pod_selector": expected_selector,
    }
    assert client.calls[0][1]["project_id"] == str(project.public_id)
    assert "namespace" not in client.calls[0][1]
    assert "expires=900" in client.calls[0][1]["s3_source_uri"]
    assert "expires=900" in client.calls[0][1]["s3_training_data_uri"]
    assert "mlflow_tracking_uri" not in client.calls[0][1]
    assert "redis_url" not in client.calls[0][1]


@pytest.mark.django_db
def test_argo_cancel_uses_job_bound_callback_capability(settings):
    user = get_user_model().objects.create_user("cancel-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="Cancel NIDS")
    job = TrainingJob.objects.create(
        project=project,
        name="cancel-nightly",
        code_snapshot_uri="s3://bucket/code.zip",
        data_snapshot_uri="s3://bucket/train.csv",
        output_uri="s3://bucket/model.tar.gz",
        status="cancelling",
    )
    client = FakeArgoClient()
    settings.ARGO_CANCEL_TRAINING_WEBHOOK_URL = "http://argo-events/cancel-train"
    settings.CONTROL_PLANE_INTERNAL_URL = "http://control-plane:8000"

    result = ArgoTrainingBackend(client=client, storage=FakeStorage()).cancel(job)

    payload = client.calls[0][1]
    assert result["dispatched"] is True
    assert payload["job_id"] == str(job.public_id)
    assert payload["job_name"] == f"training-{job.public_id}"
    assert "namespace" not in payload
    assert payload["control_plane_callback_url"].endswith(
        f"/internal/webhooks/training-jobs/{job.public_id}/cancellation/"
    )
    assert payload["cancel_reporter_capability"]
