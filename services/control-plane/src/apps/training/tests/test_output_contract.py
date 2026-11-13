import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob
from apps.training.services.artifact_selection import validate_json
from apps.training.services.output_index import index_output, public_outputs
from apps.training.services.storage_scope import expected_training_uris


class Storage:
    bucket = "test-bucket"

    def __init__(self):
        self.objects = {}
        self.client = SimpleNamespace(
            head_object=lambda **kw: {"ContentLength": len(self.objects[f"s3://{self.bucket}/{kw['Key']}"])}
        )

    def put(self, key, body, content_type="application/octet-stream"):
        raw = body.read() if hasattr(body, "read") else body
        uri = f"s3://{self.bucket}/{key}"
        self.objects[uri] = raw
        return SimpleNamespace(
            uri=uri, checksum=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw), content_type=content_type, key=key
        )

    def upload_fileobj(self, body, key, content_type, **kwargs):
        return self.put(key, body, content_type)

    def head(self, uri):
        raw = self.objects[uri]
        return SimpleNamespace(size_bytes=len(raw), checksum=hashlib.sha256(raw).hexdigest())

    def copy(self, uri, key):
        return self.put(key, self.objects[uri])

    def delete_prefix(self, prefix):
        for uri in list(self.objects):
            if uri.startswith(f"s3://{self.bucket}/{prefix}"):
                del self.objects[uri]

    def open_stream(self, uri):
        return io.BytesIO(self.objects[uri]), len(self.objects[uri]), "application/octet-stream"

    def read(self, uri, max_bytes=None):
        raw = self.objects[uri]
        if max_bytes and len(raw) > max_bytes:
            raise ValueError("Too large")
        return raw

    def delete(self, uri):
        self.objects.pop(uri, None)

    def parse_uri(self, uri):
        return self.bucket, uri.split("/", 3)[3]

    def presigned_get(self, uri, *args):
        return "https://storage.invalid/" + uri.split("/", 3)[3]


@pytest.fixture
def output_job(db, tmp_path, monkeypatch):
    owner = get_user_model().objects.create_user("output-v2@example.test", "test-password")
    job = TrainingJob.objects.create(
        owner=owner,
        status="uploading",
        model_flavor="xgboost",
        storage_layout="tenant",
        vcpu=1,
        memory_mb=1024,
        max_runtime_seconds=600,
        submitted_at=timezone.now(),
    )
    job.output_uri = expected_training_uris(job, Storage.bucket)["output"]
    job.save()
    spec = importlib.util.spec_from_file_location(
        "output_contract_v2", Path(__file__).resolve().parents[6] / "services/training-runner/src/output_contract.py"
    )
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    model, metadata, system = (tmp_path / name for name in ("model", "metadata", "system"))
    for folder in (model, metadata, system):
        folder.mkdir()
    (model / "first.joblib").write_bytes(b"first")
    (model / "second.joblib").write_bytes(b"second")
    (metadata / "not-called-metrics.json").write_text('{"accuracy":0.9}')
    (metadata / "labels.json").write_text('{"0":"BENIGN","1":"ATTACK"}')
    (system / "stdout.txt").write_text("internal logs")
    archive = tmp_path / "package.tar.gz"
    contract.package(archive, model, metadata, system, job.model_flavor)
    storage = Storage()
    storage.objects[job.output_uri] = archive.read_bytes()
    for module in (
        "apps.training.services.artifact_selection",
        "apps.training.services.project_assignment",
        "apps.training.services.outputs",
        "apps.training.services.snapshots",
        "apps.training.services.downloads",
    ):
        monkeypatch.setattr(module + ".S3Storage", lambda **kwargs: storage)
    return owner, job, storage


def publish(job, storage):
    index_output(job, storage)
    job.status = "completed"
    job.save(update_fields=["status"])


def test_index_is_complete_idempotent_and_hides_system_files(output_job):
    _, job, storage = output_job
    publish(job, storage)
    assert public_outputs(job).count() == 4
    assert {a.relative_path.split("/")[0] for a in public_outputs(job)} == {"Model", "Metadata"}
    keys = set(storage.objects)
    index_output(job, storage)
    assert set(storage.objects) == keys
    assert job.outputs.filter(metadata__group="_mlops").count() == 2
    assert not job.outputs.filter(s3_uri=job.output_uri).exists()


def test_select_model_and_metadata_manually_and_replay(output_job):
    owner, job, storage = output_job
    publish(job, storage)
    project = ModelProject.objects.create(owner=owner, name="Selected artifacts")
    model = job.outputs.get(relative_path="Model/second.joblib")
    metrics = job.outputs.get(relative_path="Metadata/not-called-metrics.json")
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/training-jobs/{job.public_id}/project/"
    payload = {"project_id": str(project.public_id), "output_revision": 1}
    assert client.post(url, payload, format="json").status_code == 400
    payload.update(model_id=str(model.public_id), artifacts={"metrics": str(metrics.public_id)})
    assert client.post(url, payload, format="json").status_code == 200
    assert client.post(url, payload, format="json").status_code == 200
    job.refresh_from_db()
    assert job.artifact_selection["model_id"] == str(model.public_id)
    assert job.artifact_selection["artifacts"] == {"metrics": str(metrics.public_id)}
    assert job.output_revision == 2
    assert job.outputs.get(pk=model.pk).s3_uri != job.output_uri


def test_save_upload_and_project_creation_are_atomic(output_job):
    owner, job, storage = output_job
    publish(job, storage)
    client = APIClient()
    client.force_authenticate(owner)
    model = job.outputs.get(relative_path="Model/first.joblib")
    import uuid

    project_id = str(uuid.uuid4())
    payload = {
        "new_project": json.dumps({"id": project_id, "name": "Atomic project"}),
        "output_revision": 999,
        "model_id": str(model.public_id),
        "artifacts": "{}",
        "metrics_file": SimpleUploadedFile("test.json", b'{"score":1}'),
    }
    before = set(storage.objects)
    assert client.post(f"/api/training-jobs/{job.public_id}/project/", payload, format="multipart").status_code == 409
    assert not ModelProject.objects.filter(public_id=project_id).exists()
    assert set(storage.objects) == before


def test_public_download_never_returns_private_archive(output_job):
    owner, job, storage = output_job
    publish(job, storage)
    client = APIClient()
    client.force_authenticate(owner)
    response = client.get(f"/api/training-jobs/{job.public_id}/")
    assert response.status_code == 200
    assert len(response.data["outputs"]) == 4
    response = client.get(f"/api/training-jobs/{job.public_id}/outputs/download/", {"path": "_mlops"})
    assert response.status_code in {400, 404}


@pytest.mark.parametrize(
    "slot,raw",
    [
        ("metrics", b'{"accuracy":true}'),
        ("params", b"[]"),
        ("label_mapping", b"{}"),
        ("metrics", b'{"accuracy":1e999}'),
        ("params", b'{"value":NaN}'),
    ],
)
def test_rejects_bad_advanced_json(slot, raw):
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        validate_json(raw, slot)


def test_failed_index_never_publishes_partial_files_and_can_retry(output_job, monkeypatch):
    _, job, storage = output_job
    original = storage.upload_fileobj
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("temporary storage failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(storage, "upload_fileobj", fail_second)
    with pytest.raises(OSError):
        index_output(job, storage)
    assert not public_outputs(job).exists()
    assert set(storage.objects) == {job.output_uri}
    monkeypatch.setattr(storage, "upload_fileobj", original)
    publish(job, storage)
    assert public_outputs(job).count() == 4


def test_async_completion_preserves_runtime_end_and_is_idempotent(output_job, monkeypatch):
    from datetime import timedelta

    from apps.training.services.output_finalization import finalize_output

    _, job, storage = output_job
    end = timezone.now() - timedelta(minutes=5)
    job.runtime_started_at = end - timedelta(seconds=30)
    job.tracking = {"output_runtime_finished_at": end.isoformat()}
    job.save()
    monkeypatch.setattr("apps.training.services.output_finalization._notify_result", lambda job: None)
    finalize_output.run(str(job.public_id))
    job.refresh_from_db()
    assert job.status == "completed"
    assert job.completed_at == end
    assert job.runtime_seconds == 30
    assert job.observation_status == "cleanup_pending"
    before = set(storage.objects)
    finalize_output.run(str(job.public_id))
    assert set(storage.objects) == before


def test_cancelled_job_cannot_publish_output(output_job):
    from apps.training.services.output_finalization import finalize_output

    _, job, storage = output_job
    job.status = "cancelled"
    job.save()
    finalize_output.run(str(job.public_id))
    with pytest.raises(ValueError, match="no longer"):
        index_output(job, storage)
    assert not job.outputs.exists()
    assert set(storage.objects) == {job.output_uri}


def test_build_uses_exact_selection_without_tracking_or_filename_fallback(output_job, monkeypatch):
    from apps.deployment.services.builds import request_training_build
    from apps.training.services.project_assignment import assign_project

    owner, job, storage = output_job
    publish(job, storage)
    project = ModelProject.objects.create(owner=owner, name="Exact selection")
    model = job.outputs.get(relative_path="Model/second.joblib")
    metadata = job.outputs.get(relative_path="Metadata/not-called-metrics.json")
    monkeypatch.setattr("apps.deployment.services.builds._enqueue", lambda build: None)
    assigned = assign_project(
        job=job,
        actor=owner,
        data={
            "project_id": project.public_id,
            "output_revision": 1,
            "model_id": model.public_id,
            "artifacts": {"metrics": str(metadata.public_id)},
        },
    )
    build, _ = request_training_build(job=assigned, backend="docker", storage=storage)
    selected = build.input_assets.get(kind="training_output")
    assert storage.objects[selected.s3_uri] == b"second"
    assert build.metrics_summary == {"accuracy": 0.9}
    assert not build.input_assets.filter(kind="label_mapping").exists()
    assert not build.params_summary
    assert not build.insights_summary
    build.status = "ready"
    build.save()
    # A later assignment clears optional slots; the old Build remains immutable.
    assigned = assign_project(
        job=assigned,
        actor=owner,
        data={"project_id": project.public_id, "output_revision": 2, "model_id": model.public_id, "artifacts": {}},
    )
    newer, _ = request_training_build(job=assigned, backend="docker", storage=storage)
    assert newer.metrics_summary == {}
    build.refresh_from_db()
    assert build.metrics_summary == {"accuracy": 0.9}
    assert build.source_output_revision == 2


def test_assignment_rejects_model_tampering_and_cross_tenant_access(output_job):
    owner, job, storage = output_job
    publish(job, storage)
    project = ModelProject.objects.create(owner=owner, name="Protected")
    model = job.outputs.get(relative_path="Model/first.joblib")
    storage.objects[model.s3_uri] = b"changed"
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/training-jobs/{job.public_id}/project/"
    payload = {"project_id": str(project.public_id), "output_revision": 1, "model_id": str(model.public_id)}
    assert client.post(url, payload, format="json").status_code == 400
    job.refresh_from_db()
    assert job.project_id is None
    other = get_user_model().objects.create_user("other-output@example.test", "password")
    client.force_authenticate(other)
    assert client.get(f"/api/training-jobs/{job.public_id}/").status_code == 404
    assert client.post(url, payload, format="json").status_code == 404


def test_concurrent_index_attempts_do_not_delete_winning_files(output_job, monkeypatch):
    _, job, storage = output_job
    upload = storage.upload_fileobj
    entered = False

    def competing_upload(*args, **kwargs):
        nonlocal entered
        result = upload(*args, **kwargs)
        if not entered:
            entered = True
            index_output(TrainingJob.objects.get(pk=job.pk), storage)
        return result

    monkeypatch.setattr(storage, "upload_fileobj", competing_upload)
    index_output(job, storage)
    assert public_outputs(job).count() == 4
    assert set(storage.objects) == {job.output_uri, *job.outputs.values_list("s3_uri", flat=True)}


def test_internal_files_are_indexed_but_never_downloadable_and_archive_is_deleted(
    output_job, monkeypatch, django_capture_on_commit_callbacks
):
    from unittest.mock import Mock

    from apps.training.services.output_finalization import cleanup_output_archive
    from apps.training.services.outputs import verify_training_output

    owner, job, storage = output_job
    queued = Mock()
    monkeypatch.setattr(cleanup_output_archive, "delay", queued)
    monkeypatch.setattr("infrastructure.storage.S3Storage", lambda: storage)
    with django_capture_on_commit_callbacks(execute=True):
        publish(job, storage)
    queued.assert_called_once_with(str(job.public_id))
    internal = job.outputs.filter(metadata__group="_mlops")
    assert internal.count() == 2
    assert all("/output/internal/" in row.s3_uri for row in internal)
    assert storage.objects[internal.get(relative_path="_mlops/stdout.txt").s3_uri] == b"internal logs"
    client = APIClient()
    client.force_authenticate(owner)
    for row in internal:
        assert client.get(f"/api/training-jobs/{job.public_id}/outputs/{row.public_id}/download/").status_code == 404
    assert client.get(f"/api/training-jobs/{job.public_id}/outputs/download/", {"path": "_mlops"}).status_code == 404
    assert len(client.get(f"/api/training-jobs/{job.public_id}/").data["outputs"]) == 4
    from zipfile import ZipFile

    response = client.get(f"/api/training-jobs/{job.public_id}/outputs/download/")
    assert response.status_code == 200
    with ZipFile(io.BytesIO(b"".join(response.streaming_content))) as bundle:
        assert len(bundle.namelist()) == 4
        assert not any("_mlops" in name or "model.tar.gz" in name for name in bundle.namelist())
    cleanup_output_archive.run(str(job.public_id))
    assert job.output_uri not in storage.objects
    assert all(row.s3_uri in storage.objects for row in job.outputs.all())
    # Worker restart between index commit and completion needs no original archive.
    verify_training_output(job, storage)
    cleanup_output_archive.run(str(job.public_id))
    assert public_outputs(job).count() == 4


def test_archive_cleanup_failure_keeps_index_and_can_retry(output_job, monkeypatch):
    from unittest.mock import Mock

    from apps.training.services.output_finalization import cleanup_output_archive

    _, job, storage = output_job
    publish(job, storage)
    monkeypatch.setattr("infrastructure.storage.S3Storage", lambda: storage)
    delete = storage.delete
    monkeypatch.setattr(storage, "delete", Mock(side_effect=TimeoutError("temporary storage outage")))
    with pytest.raises(TimeoutError):
        cleanup_output_archive.run(str(job.public_id))
    assert job.output_uri in storage.objects
    assert public_outputs(job).count() == 4
    assert cleanup_output_archive.max_retries is None
    monkeypatch.setattr(storage, "delete", delete)
    cleanup_output_archive.run(str(job.public_id))
    assert job.output_uri not in storage.objects


def test_uploads_all_six_slots_without_changing_preview_or_original_metadata(output_job):
    owner, job, storage = output_job
    publish(job, storage)
    project = ModelProject.objects.create(owner=owner, name="Explicit uploads")
    model = job.outputs.get(relative_path="Model/first.joblib")
    original = dict(storage.objects)
    slots = {
        "label_mapping": {"0": "BENIGN", "1": "ATTACK"},
        "input_schema": {"type": "object", "properties": {"x": {"type": "number"}}},
        "metrics": {"accuracy": 0.4},
        "params": {"learning_rate": 0.1},
        "model_insights": {"baseline": 0.1, "bias": 0.2},
        "feature_importance": {"feature_importance": {"x": 0.5}},
    }
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/training-jobs/{job.public_id}/project/"

    def payload():
        return {
            "project_id": str(project.public_id),
            "output_revision": 1,
            "model_id": str(model.public_id),
            **{
                slot + "_file": SimpleUploadedFile("arbitrary.json", json.dumps(value).encode())
                for slot, value in slots.items()
            },
        }

    assert client.post(url, payload(), format="multipart").status_code == 200
    job.refresh_from_db()
    assert set(job.artifact_selection["artifacts"]) == set(slots)
    assert public_outputs(job).count() == 10
    assert not project.preview.assets.exists()
    assert all(storage.objects[key] == value for key, value in original.items())
    saved = set(storage.objects)
    assert client.post(url, payload(), format="multipart").status_code == 200
    assert set(storage.objects) == saved


def test_checksum_mismatch_rolls_back_entire_index(output_job):
    import tarfile

    _, job, storage = output_job
    result = io.BytesIO()
    with (
        tarfile.open(fileobj=io.BytesIO(storage.objects[job.output_uri])) as source,
        tarfile.open(fileobj=result, mode="w:gz") as archive,
    ):
        for member in source:
            raw = source.extractfile(member).read()
            if member.name == "_mlops/output_manifest.json":
                manifest = json.loads(raw)
                manifest["files"][0]["checksum"] = "wrong"
                raw = json.dumps(manifest).encode()
                member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    storage.objects[job.output_uri] = result.getvalue()
    with pytest.raises(ValueError, match="manifest"):
        index_output(job, storage)
    assert not public_outputs(job).exists()
    assert set(storage.objects) == {job.output_uri}


def test_output_purge_clears_selection_and_preserves_input(output_job, monkeypatch):
    from apps.training.services.jobs import request_output_purge
    from apps.training.tasks import purge_training_job_outputs

    _, job, storage = output_job
    publish(job, storage)
    model = public_outputs(job).get(relative_path="Model/first.joblib")
    job.artifact_selection = {"model_id": str(model.public_id), "artifacts": {}}
    job.save()
    input_uri = expected_training_uris(job, storage.bucket)["code"]
    storage.objects[input_uri] = b"input snapshot"
    monkeypatch.setattr("apps.training.tasks.S3Storage", lambda: storage)
    current = request_output_purge(job)
    assert not public_outputs(current).exists()
    assert current.artifact_selection == {}
    assert current.output_revision == 2
    purge_training_job_outputs.run(str(job.public_id))
    assert set(storage.objects) == {input_uri}
