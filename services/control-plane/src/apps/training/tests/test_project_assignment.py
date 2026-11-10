import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob, TrainingOutput
from apps.training.services.storage_scope import expected_training_uris


@pytest.fixture
def unassigned_job(db, monkeypatch):
    user = get_user_model().objects.create_user("assign-owner@example.test", "password")
    job = TrainingJob(owner=user, model_flavor="sklearn", status="completed", storage_layout="tenant")
    job.output_uri = expected_training_uris(job, "bucket")["output"]
    job.save()
    TrainingOutput.objects.create(job=job, kind="model", relative_path="model.tar.gz", s3_uri=job.output_uri)
    monkeypatch.setattr("apps.training.services.project_assignment.verify_training_output", lambda job: None)
    client = APIClient()
    client.force_authenticate(user)
    return user, job, client


@pytest.mark.django_db
def test_assign_existing_project_is_idempotent_and_preserves_model(unassigned_job):
    user, job, client = unassigned_job
    project = ModelProject.objects.create(owner=user, name="Existing")
    data = {"project_id": str(project.public_id), "output_revision": 1}
    endpoint = f"/api/training-jobs/{job.public_id}/project/"
    assert client.post(endpoint, data, format="json").status_code == 200
    assert client.post(endpoint, data, format="json").status_code == 200
    job.refresh_from_db()
    assert job.project_id == project.pk
    assert job.output_uri == expected_training_uris(job, "bucket")["output"]
    other = ModelProject.objects.create(owner=user, name="Other")
    assert client.post(endpoint, {"project_id": str(other.public_id), "output_revision": 1}, format="json").status_code == 409


@pytest.mark.django_db
def test_create_project_and_assign_with_revision_check(unassigned_job):
    user, job, client = unassigned_job
    project_id = uuid.uuid4()
    endpoint = f"/api/training-jobs/{job.public_id}/project/"
    data = {"new_project": {"id": str(project_id), "name": "New project"}, "output_revision": 2}
    assert client.post(endpoint, data, format="json").status_code == 409
    assert not ModelProject.objects.filter(public_id=project_id).exists()
    data["output_revision"] = 1
    assert client.post(endpoint, data, format="json").status_code == 200
    assert client.post(endpoint, data, format="json").status_code == 200
    assert ModelProject.objects.filter(public_id=project_id, owner=user).count() == 1


@pytest.mark.django_db
def test_assignment_denies_other_users(unassigned_job):
    user, job, client = unassigned_job
    other = get_user_model().objects.create_user("assign-other@example.test", "password")
    other_project = ModelProject.objects.create(owner=other, name="Other")
    endpoint = f"/api/training-jobs/{job.public_id}/project/"
    assert client.post(endpoint, {"project_id": str(other_project.public_id), "output_revision": 1}, format="json").status_code == 404
    client.force_authenticate(other)
    assert client.post(endpoint, {"project_id": str(other_project.public_id), "output_revision": 1}, format="json").status_code == 404


@pytest.mark.django_db
def test_unassigned_model_summary_allows_editing_but_not_building(unassigned_job, monkeypatch):
    from apps.catalog.tests.test_preview_lifecycle import MemoryStorage

    _, job, client = unassigned_job
    monkeypatch.setattr("apps.training.services.outputs.S3Storage", lambda: MemoryStorage())
    response = client.get(f"/api/training-jobs/{job.public_id}/model-output/")
    assert response.status_code == 200
    assert response.data["project_id"] is None
    assert response.data["can_edit"] is True
    assert response.data["can_build"] is False
