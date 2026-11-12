from .test_job_drafts import studio as studio
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.training.api.serializers import TrainingJobSerializer, TrainingDraftSettingsSerializer
from apps.training.models import TrainingJob
from apps.training.services.resources import validate_resources


@pytest.mark.django_db
@pytest.mark.parametrize("backend,expected", [
    ("docker", [{"type": "gpu", "model": "", "counts": [1]}]),
    ("argo", [{"type": "gpu", "model": "t4", "counts": [1]}, {"type": "gpu", "model": "a10g", "counts": [1]}]),
])
def test_capabilities_never_advertise_more_than_one_gpu(settings, monkeypatch, backend, expected):
    settings.TRAINING_BACKEND = backend
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = (1, 2, 4)
    monkeypatch.setattr("apps.training.services.local_gpu.inventory", lambda **kwargs: {
        "status": "available", "reason": "", "devices": [{"id": "GPU-01234567-89ab-cdef-0123-456789abcdef"}]})
    client = APIClient()
    client.force_authenticate(get_user_model().objects.create_user("gpu-capability@example.com"))
    result = client.get("/api/training-jobs/runtime-capabilities/")
    assert result.status_code == 200
    if backend == "docker":
        expected[0]["device_id"] = "GPU-01234567-89ab-cdef-0123-456789abcdef"
    assert result.data["accelerators"] == [{"type": "none", "counts": [0]}, *expected]


@pytest.mark.parametrize("backend,kind,count,model,valid", [
    ("argo", "none", 0, "", True),
    ("argo", "gpu", 1, "t4", True),
    ("argo", "gpu", 1, "a10g", True),
    ("argo", "gpu", 1, "", False),
    ("argo", "gpu", 1, "other", False),
    ("argo", "gpu", 2, "t4", False),
    ("argo", "none", 0, "t4", False),
    ("docker", "gpu", 1, "", True),
    ("docker", "gpu", 2, "", False),
    ("docker", "gpu", 1, "t4", False),
])
def test_resource_validation(settings, backend, kind, count, model, valid):
    from rest_framework.exceptions import ValidationError

    settings.TRAINING_BACKEND = backend
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = (1, 2)
    values = {"accelerator_type": kind, "accelerator_count": count, "accelerator_model": model,
              "local_gpu_id": "GPU-01234567-89ab-cdef-0123-456789abcdef" if backend == "docker" and kind == "gpu" else ""}
    if valid:
        assert validate_resources(values) == values
    else:
        with pytest.raises(ValidationError):
            validate_resources(values)


@pytest.mark.django_db
@pytest.mark.parametrize("model", ["t4", "a10g"])
def test_serializer_persists_gpu_model_and_response(settings, model):
    settings.TRAINING_BACKEND = "argo"
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = (1,)
    user = get_user_model().objects.create_user("gpu-owner@example.com")
    project = ModelProject.objects.create(owner=user, name="gpu project")
    client = APIClient()
    client.force_authenticate(user)
    request = client.get("/").wsgi_request
    request.user = user
    serializer = TrainingDraftSettingsSerializer(data={
        "model_flavor": "pytorch", "accelerator_type": "gpu", "accelerator_count": 1,
        "accelerator_model": model}, context={"request": request})
    assert serializer.is_valid(), serializer.errors
    job = TrainingJob.objects.create(project=project, model_flavor="pytorch",
        accelerator_type="gpu", accelerator_count=1, accelerator_model=serializer.validated_data["accelerator_model"], vcpu=2, memory_mb=4096, max_runtime_seconds=3600, input_contract="legacy", status="pending")
    job.refresh_from_db()
    assert TrainingJobSerializer(job).data["accelerator_model"] == model


@pytest.mark.django_db
@pytest.mark.parametrize("model", ["t4", "a10g"])
def test_create_and_read_gpu_job_over_api(settings, monkeypatch, model):
    settings.TRAINING_BACKEND = "argo"
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = (1,)
    user = get_user_model().objects.create_user("gpu-api@example.com")
    client = APIClient()
    client.force_authenticate(user)
    payload = {"model_flavor": "pytorch",
        "accelerator_type": "gpu", "accelerator_count": 1, "accelerator_model": model}
    created = client.post("/api/training-jobs/", payload, format="json")
    assert created.status_code == 201
    assert created.data["accelerator_model"] == model
    fetched = client.get(f'/api/training-jobs/{created.data["id"]}/')
    assert fetched.status_code == 200
    assert fetched.data["accelerator_model"] == model


@pytest.mark.django_db
def test_submit_rejects_legacy_production_gpu_without_model(settings):
    settings.TRAINING_BACKEND = "argo"
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = (1,)
    user = get_user_model().objects.create_user("gpu-legacy@example.com")
    project = ModelProject.objects.create(owner=user, name="gpu project")
    job = TrainingJob.objects.create(project=project, model_flavor="pytorch",
        accelerator_type="gpu", accelerator_count=1, accelerator_model="", status="pending", vcpu=2, memory_mb=4096, max_runtime_seconds=3600, input_contract="legacy")
    client = APIClient()
    client.force_authenticate(user)
    response = client.post(f"/api/training-jobs/{job.public_id}/submit/")
    assert response.status_code == 400
    job.refresh_from_db()
    assert job.status == "pending"


@pytest.mark.django_db
@pytest.mark.parametrize("model", ["t4", "a10g"])
def test_argo_dispatch_includes_selected_gpu_model(settings, monkeypatch, model):
    from unittest.mock import Mock
    from apps.training.services.storage_scope import expected_training_uris
    from infrastructure.execution.argo_backends import ArgoTrainingBackend

    user = get_user_model().objects.create_user("gpu-dispatch@example.com")
    project = ModelProject.objects.create(owner=user, name="gpu project")
    job = TrainingJob(project=project, owner=project.owner, model_flavor="pytorch",
        accelerator_type="gpu", accelerator_count=1, accelerator_model=model, vcpu=2, memory_mb=4096, max_runtime_seconds=3600, input_contract="legacy", status="pending")
    uris = expected_training_uris(job, "test-bucket")
    job.code_snapshot_uri, job.data_snapshot_uri, job.output_uri = uris["code"], uris["data"], uris["output"]
    storage = Mock(bucket="test-bucket")
    storage.presigned_get.return_value = "https://example.invalid/object"
    backend = ArgoTrainingBackend(storage=storage)
    monkeypatch.setattr("infrastructure.execution.argo_backends.issue_capability", lambda *a, **kw: "capability")
    monkeypatch.setattr(backend, "persist_dispatch", Mock())
    monkeypatch.setattr(backend, "trigger", Mock(return_value={}))
    backend.run(job)
    payload = backend.trigger.call_args.args[0]
    assert payload["accelerator_type"] == "gpu"
    assert payload["accelerator_count"] == 1
    assert payload["accelerator_model"] == model


@pytest.mark.django_db
def test_retry_copies_gpu_model(studio, settings):
    import uuid
    from apps.training.services import workspaces
    from apps.training.services.drafts import submit_draft, clone_draft
    job, storage, _, _ = studio
    settings.TRAINING_GPU_ENABLED = True
    settings.TRAINING_GPU_COUNTS = (1,)
    job = workspaces.update_workspace(job, revision=job.revision, changes={"accelerator_type": "gpu", "accelerator_count": 1, "accelerator_model": "t4"})
    job = submit_draft(job, revision=job.revision, run_key=uuid.uuid4(), storage=storage)
    TrainingJob.objects.filter(pk=job.pk).update(status="failed")
    job.refresh_from_db()
    retry = clone_draft(job, retry=True, creation_key=uuid.uuid4(), storage=storage)
    assert retry.accelerator_model == "t4" and retry.accelerator_count == 1 and retry.status == "editing"
