import pytest
from django.contrib.auth import get_user_model

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob
from apps.training.services.storage_scope import expected_training_uris


@pytest.mark.django_db
def test_legacy_storage_scope_survives_project_detachment():
    owner = get_user_model().objects.create_user("storage-owner@example.test", "password")
    project = ModelProject.objects.create(owner=owner, name="Project")
    job = TrainingJob.objects.create(project=project, model_flavor="sklearn", vcpu=2, memory_mb=4096, max_runtime_seconds=3600, input_contract="legacy", status="pending")
    before = expected_training_uris(job, "bucket")
    job.project = None
    job.save(update_fields=["project"])
    job.refresh_from_db()
    assert expected_training_uris(job, "bucket") == before


@pytest.mark.django_db
def test_tenant_storage_scope_does_not_depend_on_project():
    owner = get_user_model().objects.create_user("independent-owner@example.test", "password")
    job = TrainingJob.objects.create(owner=owner, model_flavor="sklearn", storage_layout="tenant", vcpu=2, memory_mb=4096, max_runtime_seconds=3600, input_contract="legacy", status="pending")
    urls = expected_training_uris(job, "bucket")
    assert urls["code"] == f"s3://bucket/users/{owner.tenant_id}/training/jobs/{job.public_id}/input/code/source.zip"
    assert urls["output"].endswith("/output/model.tar.gz")
