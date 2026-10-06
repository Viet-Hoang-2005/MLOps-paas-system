from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
import pytest
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.training.models import TrainingJob, TrainingOutput


@pytest.fixture
def completed_training_job(db):
    user = get_user_model().objects.create_user("output-owner@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="Output Project")
    job = TrainingJob.objects.create(
        project=project,
        name="output-job",
        model_flavor="xgboost",
        status="completed",
        entry_point="train.py",
        code_snapshot_uri="s3://test-bucket/code.zip",
        data_snapshot_uri="s3://test-bucket/data.zip",
        output_uri="s3://test-bucket/model.tar.gz",
        output_revision=1,
    )
    TrainingOutput.objects.create(
        job=job,
        kind="model",
        relative_path="model.tar.gz",
        s3_uri="s3://test-bucket/model.tar.gz",
        checksum="sha256model",
        size_bytes=1000,
        content_type="application/gzip",
    )
    return project, job, user


@pytest.mark.django_db
def test_get_and_patch_model_output_flow(completed_training_job, monkeypatch):
    project, job, user = completed_training_job
    storage = MemoryStorage()
    monkeypatch.setattr("apps.training.services.outputs.S3Storage", lambda: storage)

    client = APIClient()
    client.force_authenticate(user)

    # 1. GET output summary
    get_res = client.get(f"/api/training-jobs/{job.public_id}/model-output/")
    assert get_res.status_code == 200
    assert get_res.data["output_revision"] == 1
    assert get_res.data["model_flavor"] == "xgboost"
    assert get_res.data["can_edit"] is True
    assert get_res.data["can_build"] is True
    assert get_res.data["model_artifact"]["name"] == "model.tar.gz"
    assert get_res.data["source_code"] is None
    assert get_res.data["reference_data"] is None

    # 2. PATCH to add source code and reference data
    py_content = b"print('hello world')\n"
    csv_content = b"feature1,label\n1.0,0\n2.0,1\n"
    patch_res = client.patch(
        f"/api/training-jobs/{job.public_id}/model-output/",
        {
            "output_revision": 1,
            "source_code_file": SimpleUploadedFile("custom.py", py_content, "text/x-python"),
            "reference_data_file": SimpleUploadedFile("baseline.csv", csv_content, "text/csv"),
        },
        format="multipart",
    )
    assert patch_res.status_code == 200
    assert patch_res.data["output_revision"] == 2
    assert patch_res.data["source_code"]["name"] == "custom.py"
    assert patch_res.data["reference_data"]["name"] == "baseline.csv"

    job.refresh_from_db()
    assert job.output_revision == 2
    assert job.entry_point == "train.py"

    # 3. GET reference preview
    prev_res = client.get(f"/api/training-jobs/{job.public_id}/reference-preview/")
    assert prev_res.status_code == 200
    assert prev_res.data["filename"] == "baseline.csv"
    assert prev_res.data["columns"] == ["feature1", "label"]
    assert len(prev_res.data["rows"]) == 2

    # 4. PATCH with stale revision returns 409 Conflict
    conflict_res = client.patch(
        f"/api/training-jobs/{job.public_id}/model-output/",
        {
            "output_revision": 1,  # Out of date!
            "source_code_file": SimpleUploadedFile("new.py", b"pass", "text/x-python"),
        },
        format="multipart",
    )
    assert conflict_res.status_code == 409


@pytest.mark.django_db
def test_model_output_mutation_requires_valid_revision(completed_training_job, monkeypatch):
    _, job, user = completed_training_job
    storage = MemoryStorage()
    monkeypatch.setattr("apps.training.services.outputs.S3Storage", lambda: storage)
    client = APIClient()
    client.force_authenticate(user)

    missing = client.patch(
        f"/api/training-jobs/{job.public_id}/model-output/",
        {"source_code_file": SimpleUploadedFile("main.py", b"print(1)\n", "text/x-python")},
        format="multipart",
    )
    invalid = client.patch(
        f"/api/training-jobs/{job.public_id}/model-output/",
        {
            "output_revision": "not-a-number",
            "source_code_file": SimpleUploadedFile("main.py", b"print(1)\n", "text/x-python"),
        },
        format="multipart",
    )

    assert missing.status_code == 400
    assert invalid.status_code == 400
    job.refresh_from_db()
    assert job.output_revision == 1
    assert job.entry_point == "train.py"
    assert not job.outputs.filter(kind="source_code").exists()
