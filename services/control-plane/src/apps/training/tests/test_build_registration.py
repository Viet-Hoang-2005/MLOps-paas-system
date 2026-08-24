from types import SimpleNamespace

import pytest
from common.api.exceptions import Conflict
from django.contrib.auth import get_user_model
from infrastructure.storage.s3 import StoredObject
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.deployment.models import Build
from apps.deployment.services import builds as build_service
from apps.registry.models import ModelMetric, ModelVersion
from apps.registry.services.versions import register_successful_build
from apps.training.models import TrainingJob, TrainingOutput
from apps.training.services import jobs as job_service


class FakeStorage:
    def __init__(self):
        self.copies = []
        self.deleted = []

    def copy(self, source_uri, destination_key):
        self.copies.append((source_uri, destination_key))
        return StoredObject(destination_key, f"s3://bucket/{destination_key}", "copied", 42, "application/gzip")

    def delete_prefix(self, prefix):
        self.deleted.append(prefix)


class FakeImageRegistry:
    def promote(self, *, build, version, image_uri, image_digest=""):
        return f"image-{build.project.public_id}:v{version.version}", image_digest or "sha256:local"


def completed_job(email="training-build@example.com"):
    owner = get_user_model().objects.create_user(email, "password123")
    project = ModelProject.objects.create(owner=owner, name="NIDS")
    job = TrainingJob.objects.create(
        project=project,
        name="training-v1",
        model_flavor="xgboost",
        requirements_text="xgboost==2.0.3",
        code_snapshot_uri="s3://bucket/source.zip",
        data_snapshot_uri="s3://bucket/reference.csv",
        output_uri="s3://bucket/model.tar.gz",
        status="completed",
    )
    TrainingOutput.objects.create(
        job=job,
        kind="model",
        relative_path="model.tar.gz",
        s3_uri=job.output_uri,
        checksum="output-checksum",
        size_bytes=42,
        content_type="application/gzip",
    )
    return job


@pytest.mark.django_db
def test_training_build_reuses_active_attempt_and_snapshots_output(monkeypatch, django_capture_on_commit_callbacks):
    job = completed_job()
    storage = FakeStorage()
    queued = []
    monkeypatch.setattr(
        build_service.execute_build,
        "delay",
        lambda build_id: queued.append(build_id) or SimpleNamespace(id="task-id"),
    )

    with django_capture_on_commit_callbacks(execute=True):
        first, created = build_service.request_training_build(job=job, backend="docker", storage=storage)
    second, second_created = build_service.request_training_build(job=job, backend="docker", storage=storage)

    assert created is True
    assert second_created is False
    assert second.pk == first.pk
    assert first.source_job == job
    assert first.flavor == "xgboost"
    assert first.requirements_snapshot == "xgboost==2.0.3"
    assert first.input_assets.get().kind == "training_output"
    assert queued == [str(first.public_id)]


@pytest.mark.django_db
def test_training_build_requires_completed_output():
    job = completed_job("training-no-output@example.com")
    job.outputs.all().delete()

    with pytest.raises(ValidationError, match="no model output"):
        build_service.request_training_build(job=job, backend="docker", storage=FakeStorage())


@pytest.mark.django_db
def test_successful_training_build_creates_one_version_with_summaries():
    job = completed_job("training-register@example.com")
    build = Build.objects.create(
        project=job.project,
        source_job=job,
        flavor=job.model_flavor,
        artifact_format="training_output",
        requirements_snapshot=job.requirements_text,
        status="building",
    )
    output = job.outputs.get(kind="model")
    build.input_assets.create(
        kind="training_output",
        name=output.relative_path,
        s3_uri=output.s3_uri,
        checksum=output.checksum,
        size_bytes=output.size_bytes,
    )
    storage = FakeStorage()

    first = register_successful_build(
        build=build,
        image_uri=f"image-{job.project.public_id}:build-{build.public_id}",
        image_digest="sha256:training",
        metrics_summary={"accuracy": 0.98},
        params_summary={"max_depth": 8},
        insights_summary={"classes": ["normal", "attack"]},
        storage=storage,
        image_registry=FakeImageRegistry(),
    )
    replay = register_successful_build(
        build=build,
        image_uri=f"image-{job.project.public_id}:build-{build.public_id}",
        image_digest="sha256:training",
        storage=storage,
        image_registry=FakeImageRegistry(),
    )

    assert first.version_id == replay.version_id
    assert ModelVersion.objects.filter(source_job=job).count() == 1
    assert first.version.source_job == job
    assert first.version.version == "1"
    assert first.version.params_summary == {"max_depth": 8}
    assert ModelMetric.objects.get(version=first.version, name="accuracy").value == 0.98


@pytest.mark.django_db
def test_output_purge_is_blocked_while_build_active(monkeypatch):
    job = completed_job("training-purge-active@example.com")
    Build.objects.create(project=job.project, source_job=job, flavor="xgboost", status="building")
    monkeypatch.setattr(job_service.purge_training_job_outputs, "delay", lambda *_args: None)

    with pytest.raises(Conflict, match="active model build"):
        job_service.request_output_purge(job)


@pytest.mark.django_db
def test_output_purge_keeps_job_and_enqueues_bundle_deletion(monkeypatch, django_capture_on_commit_callbacks):
    job = completed_job("training-purge@example.com")
    enqueued = []
    monkeypatch.setattr(job_service.purge_training_job_outputs, "delay", lambda job_id: enqueued.append(job_id))

    with django_capture_on_commit_callbacks(execute=True):
        updated = job_service.request_output_purge(job)

    assert updated.outputs_purged_at is not None
    assert TrainingJob.objects.filter(pk=job.pk).exists()
    assert enqueued == [str(job.public_id)]


@pytest.mark.django_db
def test_training_build_and_output_delete_are_tenant_scoped():
    job = completed_job("training-owner@example.com")
    other = get_user_model().objects.create_user("training-other@example.com", "password123")
    client = APIClient()
    client.force_authenticate(other)

    assert client.post(f"/api/training-jobs/{job.public_id}/build/").status_code == 404
    assert client.delete(f"/api/training-jobs/{job.public_id}/outputs/").status_code == 404
