import uuid
from io import BytesIO
from zipfile import ZipFile

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.training.models import TrainingJob, TrainingJobEntry
from apps.training.services import workspaces
from apps.training.services.capabilities import issue_capability
from apps.training.services.drafts import submit_draft
from common.api.exceptions import Conflict


def run_workspace(workspace, *, revision, run_key, values, storage):
    workspace.refresh_from_db()
    for field, value in values.items():
        setattr(workspace, field, value)
    workspace.storage_layout = "tenant"
    workspace.backend = "argo"
    workspace.save()
    return submit_draft(workspace, revision=revision, run_key=run_key, storage=storage)


@pytest.fixture
def draft(db, settings, monkeypatch):
    settings.TRAINING_BACKEND = "argo"
    settings.TRAINING_ENABLED = True
    settings.TRAINING_EXECUTION_WATCH_ENABLED = True
    user = get_user_model().objects.create_user("workspace-run@example.test", "test-password")
    workspace = TrainingJob.objects.create(owner=user, entry_point="train.py")
    storage = MemoryStorage()
    payload = b"import os\nprint(os.environ['SM_MODEL_DIR'])\n"
    item = storage.put(f"users/{user.tenant_id}/training/jobs/{workspace.public_id}/draft/objects/script", payload)
    TrainingJobEntry.objects.create(
        job=workspace,
        relative_path="train.py",
        kind="script",
        s3_uri=item.uri,
        checksum=item.checksum,
        size_bytes=item.size_bytes,
    )
    monkeypatch.setattr("apps.training.services.jobs._enqueue", lambda job: None)
    values = {
        "model_flavor": "sklearn",
        "vcpu": 1,
        "memory_mb": 2048,
        "max_runtime_seconds": 900,
        "accelerator_type": "none",
        "accelerator_count": 0,
    }
    return workspace, storage, values


@pytest.mark.django_db
def test_run_without_project_is_immutable_and_idempotent(draft):
    workspace, storage, values = draft
    key = uuid.uuid4()
    job = run_workspace(workspace, revision=1, run_key=key, values=values, storage=storage)
    assert job.project_id is None
    assert job.owner_id == workspace.owner_id
    assert job.status == "queued"
    assert job.input_contract == "workspace"
    assert str(job) == str(job.public_id)
    assert run_workspace(workspace, revision=1, run_key=key, values=values, storage=storage).pk == job.pk
    with pytest.raises(Conflict):
        workspaces.update_workspace(workspace, revision=1, changes={"environment": {"EXAMPLE": "changed"}})
    with ZipFile(BytesIO(storage.objects[job.code_snapshot_uri])) as archive:
        assert archive.namelist() == ["train.py"]
    from apps.training.models import TrainingQuotaReservation

    assert TrainingQuotaReservation.objects.filter(job_id=job.public_id, owner=workspace.owner, active=True).exists()


@pytest.mark.django_db
def test_runtime_configuration_is_job_bound_and_one_time(draft, settings):
    from cryptography.fernet import Fernet

    workspace, storage, values = draft
    settings.TRAINING_SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    secret, revision = workspaces.set_secret(workspace, revision=1, name="EXAMPLE_KEY", value="synthetic-example-value")
    job = run_workspace(workspace, revision=revision, run_key=uuid.uuid4(), values=values, storage=storage)
    token = issue_capability(job, "runtime_config")
    client = APIClient()
    endpoint = f"/internal/training-jobs/{job.public_id}/runtime-config/"
    assert client.post(endpoint, HTTP_AUTHORIZATION="Bearer wrong").status_code == 403
    response = client.post(endpoint, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response.data["environment"]["EXAMPLE_KEY"] == "synthetic-example-value"
    assert client.post(endpoint, HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 403
    client.force_authenticate(workspace.owner)
    detail = client.get(f"/api/training-jobs/{job.public_id}/")
    assert detail.status_code == 200
    assert "secret_snapshot" not in detail.data
    assert "environment_snapshot" not in detail.data


@pytest.mark.django_db
def test_unassigned_argo_dispatch_has_job_identity_and_no_secret_values(draft):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from infrastructure.execution.argo_backends import ArgoTrainingBackend

    workspace, storage, values = draft
    job = run_workspace(workspace, revision=1, run_key=uuid.uuid4(), values=values, storage=storage)
    client = SimpleNamespace(trigger=Mock(return_value={"accepted": True}))
    backend = ArgoTrainingBackend(client=client, storage=storage)
    backend.run(job)
    payload = client.trigger.call_args.args[1]
    assert payload["project_id"] == ""
    assert payload["tenant_id"] == workspace.owner.tenant_id
    assert payload["job_id"] == str(job.public_id)
    assert payload["input_contract"] == "workspace"
    assert "environment_snapshot" not in payload
    assert "secret_snapshot" not in payload
    assert payload["runtime_config_url"].endswith(f"/{job.public_id}/runtime-config/")


@pytest.mark.django_db
def test_retry_rechecks_secret_access_after_copy(draft, settings):
    from cryptography.fernet import Fernet

    from apps.training.models import TrainingJob
    from apps.training.services.jobs import retry_job

    workspace, storage, values = draft
    settings.TRAINING_SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    secret, revision = workspaces.set_secret(workspace, revision=1, name="EXAMPLE_KEY", value="synthetic-value")
    original = run_workspace(workspace, revision=revision, run_key=uuid.uuid4(), values=values, storage=storage)
    TrainingJob.objects.filter(pk=original.pk).update(status="failed")
    original.refresh_from_db()
    put = storage.put

    def copy_then_revoke(*args, **kwargs):
        result = put(*args, **kwargs)
        original.secrets.all().delete()
        return result

    storage.put = copy_then_revoke
    retry = retry_job(original, creation_key=uuid.uuid4(), storage=storage)
    assert retry.status == "editing" and not retry.secrets.exists()
    assert original.code_snapshot_uri in storage.objects
