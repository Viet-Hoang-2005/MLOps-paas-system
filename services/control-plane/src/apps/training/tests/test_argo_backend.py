from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.training.tests.factories import training_job
from apps.catalog.models import ModelProject
from apps.training.services.storage_scope import expected_training_uris
from infrastructure.execution.argo_backends import ArgoTrainingBackend


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
    job = training_job(
        project=project,
        code_snapshot_uri="s3://bucket/code.zip",
        data_snapshot_uri="s3://bucket/train.csv",
        output_uri="s3://bucket/model.tar.gz",
        vcpu=2,
        memory_mb=4096,
        max_runtime_seconds=3600,
        input_contract="legacy",
        status="queued",
        submitted_at=timezone.now(),
    )
    scoped_uris = expected_training_uris(job, "bucket")
    job.code_snapshot_uri = scoped_uris["code"]
    job.data_snapshot_uri = scoped_uris["data"]
    job.output_uri = scoped_uris["output"]
    job.save(update_fields=["code_snapshot_uri", "data_snapshot_uri", "output_uri"])
    client = FakeArgoClient()

    ArgoTrainingBackend(client=client, storage=FakeStorage()).run(job)

    job.refresh_from_db()
    runtime_name = f"training-{job.public_id}"
    expected_selector = f"mlops-paas.io/training-job-id={job.public_id}"
    assert job.external_job_id == runtime_name
    assert job.tracking["runtime"] == {
        "backend": "argo",
        "namespace": "mlops-paas-training",
        "train_job_name": runtime_name,
        "workflow_selector": expected_selector,
        "pod_selector": expected_selector,
    }
    assert client.calls[0][1]["project_id"] == str(project.public_id)
    assert "namespace" not in client.calls[0][1]
    assert "expires=900" in client.calls[0][1]["s3_source_uri"]
    assert "expires=900" in client.calls[0][1]["s3_training_data_uri"]
    assert client.calls[0][1]["mlflow_tracking_uri"] == "http://control-plane:8000"
    assert "mlflow_tracking_token" in client.calls[0][1]
    assert "redis_url" not in client.calls[0][1]


@pytest.mark.django_db
@pytest.mark.parametrize("expire_lease", [False, True])
def test_argo_cancel_uses_job_bound_callback_capability(settings, expire_lease):
    user = get_user_model().objects.create_user("cancel-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="Cancel NIDS")
    job = training_job(
        project=project,
        code_snapshot_uri="s3://bucket/code.zip",
        data_snapshot_uri="s3://bucket/train.csv",
        output_uri="s3://bucket/model.tar.gz",
        backend="argo",
        status="cancelling",
        vcpu=2,
        memory_mb=4096,
        max_runtime_seconds=3600,
        input_contract="legacy",
        submitted_at=timezone.now(),
    )
    client = FakeArgoClient()
    settings.ARGO_RECONCILE_WEBHOOK_URL = "http://argo-events/reconcile"
    settings.CONTROL_PLANE_INTERNAL_URL = "http://control-plane:8000"

    backend = ArgoTrainingBackend(client=client, storage=FakeStorage())
    result = backend.cancel(job)

    url, payload = client.calls[0]
    assert url == "http://argo-events/reconcile"
    assert result["dispatched"] is True
    assert result["confirmed"] is False
    assert payload["kind"] == "training"
    assert payload["resource_id"] == str(job.public_id)
    assert payload["tenant_id"] == job.owner.tenant_id
    assert payload["project_id"] == str(project.public_id)
    assert payload["stop"] is True
    assert payload["callback_url"].endswith(
        f"/internal/executions/training/{job.public_id}/observations/"
    )
    assert payload["callback_token"]

    job.refresh_from_db()
    original_lease = job.execution_check_token
    original_expiry = job.execution_check_lease_until
    if expire_lease:
        type(job).objects.filter(pk=job.pk).update(execution_check_lease_until=timezone.now() - timedelta(seconds=1))

    repeated = backend.cancel(job)
    job.refresh_from_db()
    assert repeated["confirmed"] is False
    assert repeated["dispatched"] is expire_lease
    assert len(client.calls) == (2 if expire_lease else 1)
    assert (job.execution_check_token != original_lease) is expire_lease
    if not expire_lease:
        assert job.execution_check_lease_until == original_expiry

    callback = APIClient()
    url = f"/internal/executions/training/{job.public_id}/observations/"

    def report(token):
        return callback.post(url, {"status": "stopped"}, format="json", HTTP_AUTHORIZATION=f"Bearer {token}")

    if expire_lease:
        assert report(payload["callback_token"]).status_code == 403
    response = report(client.calls[-1][1]["callback_token"])
    assert response.status_code == 200
    assert response.data["status"] == "cancelled"
    assert backend.cancel(job) == {"confirmed": True, "dispatched": False}
    assert len(client.calls) == (2 if expire_lease else 1)
