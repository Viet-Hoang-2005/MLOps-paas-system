from types import SimpleNamespace
import pytest
from django.contrib.auth import get_user_model
from apps.catalog.models import ModelProject
from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.training.models import TrainingJob, TrainingOutput
from apps.training.services.storage_scope import expected_training_uris
from apps.training.services.storage_migration import migrate_job_storage


class CopyStorage(MemoryStorage):
    def __init__(self):
        super().__init__()
        self.client = SimpleNamespace(get_paginator=lambda name: SimpleNamespace(paginate=self.paginate))
        self.fail_copy = False

    def paginate(self, Bucket, Prefix):
        yield {"Contents": [{"Key": uri.split("/", 3)[3]} for uri in list(self.objects) if uri.startswith(f"s3://{Bucket}/{Prefix}")]}

    def copy(self, *args, **kwargs):
        if self.fail_copy:
            raise RuntimeError("Temporary copy failure")
        return super().copy(*args, **kwargs)


@pytest.mark.django_db
def test_storage_copy_verifies_before_switching_and_resumes():
    user = get_user_model().objects.create_user("copy-owner@example.test", "test-password")
    project = ModelProject.objects.create(owner=user, name="Copy", deletion_state="deleting", is_active=False)
    job = TrainingJob(project=project, name="Old", model_flavor="sklearn", status="completed")
    storage = CopyStorage()
    uris = expected_training_uris(job, storage.bucket)
    job.code_snapshot_uri, job.data_snapshot_uri, job.output_uri, job.mlflow_artifact_uri = uris.values()
    job.save()
    for name in ("code", "data", "output"):
        storage.put(storage.parse_uri(uris[name])[1], name.encode())
    TrainingOutput.objects.create(job=job, kind="model", relative_path="model.tar.gz", s3_uri=job.output_uri)
    storage.fail_copy = True
    with pytest.raises(RuntimeError):
        migrate_job_storage(job, storage=storage)
    job.refresh_from_db()
    assert job.storage_layout == "project"
    assert job.output_uri == uris["output"]
    storage.fail_copy = False
    job = migrate_job_storage(job, storage=storage)
    assert job.storage_layout == "tenant"
    assert "/models/" not in job.output_uri
    assert storage.objects[job.output_uri] == b"output"
    assert storage.objects[uris["output"]] == b"output"  # Source remains until Project cleanup.
    assert job.outputs.get(kind="model").s3_uri == job.output_uri
    assert job.storage_copies.count() == 3
