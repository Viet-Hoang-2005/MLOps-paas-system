import hashlib
import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.catalog.services.preview import save_preview
from apps.deployment.models import Build, Deployment, Endpoint
from apps.deployment.services.builds import request_preview_build
from apps.deployment.services.completion import complete_build, request_registration
from apps.deployment.tasks import _mark_deployment_succeeded
from apps.drift.models import DriftMonitor
from apps.drift.services.monitors import create_monitor
from apps.observability.services.runtime_metrics import runtime_metrics
from apps.registry.models import ModelVersion
from apps.registry.services.versions import register_successful_build
from common.api.exceptions import Conflict
from infrastructure.storage.s3 import StoredObject
from infrastructure.storage.paths import project_prefix


class MemoryStorage:
    bucket = "test-bucket"

    def __init__(self):
        self.objects = {}
        self.deleted = []
        self.fail_copy = False

    def put(self, key, file, content_type="application/octet-stream"):
        uri = f"s3://test-bucket/{key}"
        payload = file.read() if hasattr(file, "read") else file
        if isinstance(payload, str):
            payload = payload.encode()
        self.objects[uri] = payload
        checksum = hashlib.sha256(payload).hexdigest()
        return StoredObject(key, uri, checksum, len(self.objects[uri]), content_type)

    def copy(self, uri, key, checksum=None, content_type=None, size_bytes=None, expected_etag=None):
        if self.fail_copy:
            raise RuntimeError("storage unavailable")
        payload = self.objects[uri]
        if expected_etag and expected_etag.strip('"') != hashlib.sha256(payload).hexdigest():
            raise RuntimeError("staging object changed")
        dest_uri = f"s3://{self.bucket}/{key}"
        self.objects[dest_uri] = payload
        resolved_checksum = checksum or hashlib.sha256(payload).hexdigest()
        resolved_content_type = content_type or "application/octet-stream"
        resolved_size = size_bytes if size_bytes is not None else len(payload)
        return StoredObject(key, dest_uri, resolved_checksum, resolved_size, resolved_content_type)

    def read(self, uri, max_bytes=4 * 1024 * 1024):
        value = self.objects[uri]
        if len(value) > max_bytes:
            raise ValueError("Object exceeds the allowed read size.")
        return value

    def head(self, uri):
        if uri not in self.objects:
            raise KeyError(f"Object not found: {uri}")
        payload = self.objects[uri]
        key = uri.removeprefix(f"s3://{self.bucket}/")
        checksum = hashlib.sha256(payload).hexdigest()
        return StoredObject(key, uri, checksum, len(payload), "application/octet-stream", f'"{checksum}"')

    def compute_sha256(self, uri):
        return hashlib.sha256(self.objects[uri]).hexdigest()

    def presigned_put(self, uri, expires_in=900, content_type=None, size_bytes=None):
        return f"https://{self.bucket}.s3.test/{uri}?signature=mock"

    def presigned_get(self, uri, expires_in=900):
        return f"https://{self.bucket}.s3.test/{uri}?signature=mock-get"


    @staticmethod
    def parse_uri(uri):
        return uri.removeprefix("s3://").split("/", 1)

    def delete(self, uri):
        self.deleted.append(uri)
        self.objects.pop(uri, None)

    def delete_prefix(self, prefix):
        for uri in list(self.objects):
            if uri.startswith(f"s3://test-bucket/{prefix}"):
                self.delete(uri)


@pytest.fixture
def project(db):
    user = get_user_model().objects.create_user("preview-owner@example.test", "test-password")
    return ModelProject.objects.create(owner=user, name="Preview model")


def draft(project, storage, content=b"model-v1"):
    assets = staged_assets(project, storage, [
        ("source_artifact", "model.pkl", content),
        ("source_code", "train.py", b"print('v1')"),
        ("reference_data", "reference.csv", b"x,label\n1,A\n"),
        ("label_mapping", "labels.json", b'["A", "B"]'),
        ("metrics", "metrics.json", b'{"accuracy": 0.9}'),
    ])
    return save_preview(
        project=project,
        storage=storage,
        require_artifact=True,
        data={
            "revision": project.preview.revision,
            "flavor": "xgboost",
            "requirements_text": "xgboost==2.0.3",
            "assets": assets,
        },
    )


def staged_assets(project, storage, entries):
    batch = uuid.uuid4()
    result = []
    for kind, name, payload in entries:
        key = f"staging/{project_prefix(project.owner.tenant_id, project.public_id)}/preview/{batch}/{kind}/{name}"
        stored = storage.put(key, payload)
        result.append({"kind": kind, "name": name, "s3_uri": stored.uri})
    return result


def test_preview_revision_and_snapshot_isolation(project, monkeypatch):
    storage = MemoryStorage()
    preview = draft(project, storage)
    build = request_preview_build(project=project, revision=preview.revision, backend="docker", storage=storage)
    original = build.input_assets.get(kind="source_artifact")
    save_preview(
        project=project,
        storage=storage,
        data={"revision": preview.revision, "assets": staged_assets(project, storage, [("source_artifact", "model.pkl", b"model-v2")])},
    )
    assert storage.read(original.s3_uri) == b"model-v1"
    assert build.metrics_summary == {"accuracy": 0.9}
    assert build.input_assets.filter(kind__in=("source_code", "reference_data", "label_mapping")).count() == 3
    with pytest.raises(Conflict):
        save_preview(project=project, storage=storage, data={"revision": preview.revision})


def test_replacement_wins_when_kind_is_also_marked_for_removal(project):
    storage = MemoryStorage()
    preview = draft(project, storage)
    staged = staged_assets(project, storage, [("metrics", "updated.json", b'{"accuracy": 0.95}')])

    save_preview(
        project=project,
        storage=storage,
        data={"revision": preview.revision, "assets": staged, "remove_assets": ["metrics"]},
    )

    assert project.preview.assets.get(kind="metrics").name == "updated.json"


def test_failed_snapshot_rolls_back_build(project):
    storage = MemoryStorage()
    preview = draft(project, storage)
    storage.fail_copy = True
    with pytest.raises(RuntimeError):
        request_preview_build(project=project, revision=preview.revision, backend="docker", storage=storage)
    assert not project.builds.exists()
    assert project.preview.assets.count() == 5


def test_invalid_preview_does_not_save_revision_or_assets(project):
    storage = MemoryStorage()
    with pytest.raises(ValidationError):
        save_preview(
            project=project,
            storage=storage,
            data={"revision": 1, "assets": staged_assets(project, storage, [("metrics", "metrics.json", b"not json")])},
        )
    project.preview.refresh_from_db()
    assert project.preview.revision == 1
    assert not project.preview.assets.exists()


def test_staging_change_during_copy_preserves_previous_preview(project):
    class ReplacedStagingStorage(MemoryStorage):
        replace_on_copy = False

        def copy(self, uri, key, **kwargs):
            if self.replace_on_copy and "staging/" in uri:
                self.objects[uri] = b"replaced"
            return super().copy(uri, key, **kwargs)

    storage = ReplacedStagingStorage()
    preview = draft(project, storage)
    storage.replace_on_copy = True
    previous = preview.assets.get(kind="source_artifact")
    staged = staged_assets(project, storage, [("source_artifact", "model.pkl", b"new model")])

    with pytest.raises(RuntimeError, match="staging object changed"):
        save_preview(project=project, storage=storage, data={"revision": preview.revision, "assets": staged})

    preview.refresh_from_db()
    assert preview.assets.get(kind="source_artifact").s3_uri == previous.s3_uri
    assert storage.read(previous.s3_uri) == b"model-v1"


def test_build_completion_requires_explicit_idempotent_registration(project):
    storage = MemoryStorage()
    preview = draft(project, storage)
    build = request_preview_build(project=project, revision=preview.revision, backend="docker", storage=storage)
    build = complete_build(
        build, image_uri=f"image-{project.public_id}:build-{build.public_id}", image_digest="sha256:test"
    )
    assert not project.versions.exists()
    registry = SimpleNamespace(promote=lambda **kwargs: (f"image-{project.public_id}:v1", "sha256:test"))
    register_successful_build(build=build, image_uri=build.image_uri, storage=storage, image_registry=registry)
    register_successful_build(build=build, image_uri=build.image_uri, storage=storage, image_registry=registry)
    assert project.versions.count() == 1
    assert (
        project.versions.get().artifacts.filter(kind__in=("source_code", "reference_data", "label_mapping")).count()
        == 3
    )


def test_register_double_click_only_dispatches_once(project, monkeypatch, django_capture_on_commit_callbacks):
    build = Build.objects.create(project=project, flavor="xgboost", status="ready")
    calls = []
    monkeypatch.setattr("apps.deployment.tasks.register_build.delay", lambda id: calls.append(id))
    with django_capture_on_commit_callbacks(execute=True):
        request_registration(build)
        request_registration(build)
    assert calls == [str(build.public_id)]


def test_new_and_training_project_artifact_contract_and_tenant_scope(project):
    client = APIClient()
    client.force_authenticate(project.owner)
    assert client.post("/api/models/", {"name": "Requires artifact", "flavor": "xgboost"}).status_code == 400
    response = client.post("/api/models/training-projects/", {"name": "Training only"}, format="json")
    assert response.status_code == 201
    assert ModelProject.objects.get(public_id=response.data["id"]).preview.assets.count() == 0
    other = get_user_model().objects.create_user("other-preview@example.test", "test-password")
    client.force_authenticate(other)
    assert client.get(f"/api/models/{project.public_id}/preview/").status_code == 404


def running(project, version_name="1"):
    version = ModelVersion.objects.create(project=project, version=version_name, flavor="xgboost")
    build = Build.objects.create(project=project, version=version, flavor="xgboost", status="ready")
    deployment = Deployment.objects.create(version=version, build=build, status="succeeded")
    Endpoint.objects.create(deployment=deployment, public_url="http://gateway.test", health_status="healthy")
    project.active_deployment = deployment
    project.save()
    return deployment


def test_running_handoff_disables_old_monitor_and_stops_old_after_commit(
    project, monkeypatch, django_capture_on_commit_callbacks
):
    old = running(project)
    monitor = DriftMonitor.objects.create(version=old.version, name="old", reference_uri="s3://test/ref.csv")
    version = ModelVersion.objects.create(project=project, version="2", flavor="xgboost")
    build = Build.objects.create(project=project, version=version, flavor="xgboost", status="ready")
    candidate = Deployment.objects.create(version=version, build=build, status="failed")
    _mark_deployment_succeeded(candidate)
    project.refresh_from_db()
    assert project.active_deployment_id == old.pk
    candidate.status = "deploying"
    candidate.save()
    stopped = []
    monkeypatch.setattr("apps.deployment.tasks.stop_deployment.delay", lambda id: stopped.append(id))
    monkeypatch.setattr("apps.deployment.tasks.invalidate_model_server_cache", lambda *args: None)
    monkeypatch.setattr("apps.deployment.tasks.append_deployment_log", lambda *args: None)
    monkeypatch.setattr("apps.observability.services.outbox._publish_pending", lambda: None)
    with django_capture_on_commit_callbacks(execute=True):
        _mark_deployment_succeeded(candidate)
    project.refresh_from_db()
    monitor.refresh_from_db()
    assert project.active_deployment_id == candidate.pk
    assert not monitor.is_active
    assert stopped == [str(old.public_id)]


def test_monitor_csv_fills_missing_version_reference_but_not_preview(project):
    deployment = running(project)
    storage = MemoryStorage()
    monitor = create_monitor(
        data={
            "version": deployment.version,
            "name": "manual",
            "reference_file": SimpleUploadedFile("reference.csv", b"a\n1\n"),
        },
        backend="docker",
        storage=storage,
    )
    assert storage.read(monitor.reference_uri) == b"a\n1\n"
    artifact = deployment.version.artifacts.get(kind="reference_data")
    assert storage.read(artifact.uri) == b"a\n1\n"
    assert artifact.uri != monitor.reference_uri
    assert not project.preview.assets.exists()


def test_metrics_scoped_to_active_deployment_and_missing_data_not_zero(project):
    deployment = running(project)
    deployment.backend = "argo"
    deployment.save(update_fields=["backend"])
    queries = []
    client = SimpleNamespace(enabled=True, query_range=lambda expression, **kwargs: queries.append(expression) or [])
    result = runtime_metrics(project, prometheus=client)
    assert result["status"] == "no_data"
    assert str(deployment.public_id) in queries[0]
    assert str(project.owner.tenant_id) in queries[0]
    assert str(project.public_id) in queries[2]
    with pytest.raises(ValidationError):
        runtime_metrics(project, window="invalid", prometheus=client)


def test_late_completion_does_not_resurrect_cancelled_build(project):
    build = Build.objects.create(project=project, flavor="xgboost", status="cancelled")
    assert complete_build(build, image_uri="ignored").status == "cancelled"
    assert not project.versions.exists()


def test_preview_upload_fields_exist():
    from apps.catalog.api.serializers import PreviewWriteSerializer

    assert "assets" in PreviewWriteSerializer().fields
    assert "source_artifact_file" not in PreviewWriteSerializer().fields


def test_preview_api_rejects_legacy_multipart_files(project):
    client = APIClient()
    client.force_authenticate(project.owner)
    response = client.patch(
        f"/api/models/{project.public_id}/preview/",
        {"revision": project.preview.revision, "metrics_file": SimpleUploadedFile("metrics.json", b"{}")},
        format="multipart",
    )
    assert response.status_code == 400
    assert "presigned staging URL" in str(response.data)
    project.preview.refresh_from_db()
    assert project.preview.revision == 1


def test_registration_failure_removes_partial_snapshot_and_can_retry(project):
    storage = MemoryStorage()
    preview = draft(project, storage)
    build = request_preview_build(project=project, revision=preview.revision, backend="docker", storage=storage)
    complete_build(build, image_uri="temporary")
    build.refresh_from_db()

    def fail(**kwargs):
        raise RuntimeError("registry unavailable")

    with pytest.raises(RuntimeError):
        register_successful_build(
            build=build, image_uri="temporary", storage=storage, image_registry=SimpleNamespace(promote=fail)
        )
    assert not project.versions.exists()
    assert not any("/versions/" in uri for uri in storage.objects)
    assert build.input_assets.count() == 5
    build.refresh_from_db()
    registry = SimpleNamespace(promote=lambda **kwargs: ("published", "sha256:published"))
    register_successful_build(build=build, image_uri="temporary", storage=storage, image_registry=registry)
    assert project.versions.count() == 1


def test_training_build_provenance_survives_source_job_deletion(project):
    from apps.deployment.services.builds import request_training_build
    from apps.training.models import TrainingJob, TrainingOutput

    storage = MemoryStorage()
    code = storage.put("input/code.zip", SimpleUploadedFile("code.zip", b"code"), "application/zip")
    output = storage.put("output/model.tar.gz", SimpleUploadedFile("model.tar.gz", b"model"), "application/gzip")
    source_file = storage.put("output/train.py", SimpleUploadedFile("train.py", b"print(1)"), "text/x-python")
    ref_file = storage.put("output/reference.csv", SimpleUploadedFile("reference.csv", b"x\n1\n"), "text/csv")
    job = TrainingJob.objects.create(
        project=project,
        name="trained",
        model_flavor="xgboost",
        status="completed",
        entry_point="train.py",
        code_snapshot_uri=code.uri,
    )
    TrainingOutput.objects.create(job=job, kind="model", relative_path="model.tar.gz", s3_uri=output.uri)
    TrainingOutput.objects.create(job=job, kind="source_code", relative_path="train.py", s3_uri=source_file.uri)
    TrainingOutput.objects.create(job=job, kind="reference_data", relative_path="reference.csv", s3_uri=ref_file.uri)
    build, _ = request_training_build(job=job, backend="docker", storage=storage)
    job_id = job.public_id
    complete_build(build, image_uri="temporary")
    job.delete()
    build.refresh_from_db()
    register_successful_build(
        build=build,
        image_uri="temporary",
        storage=storage,
        image_registry=SimpleNamespace(promote=lambda **kwargs: ("published", "sha256:published")),
    )
    build.refresh_from_db()
    assert build.version.source_job_reference == job_id
    assert build.version.artifacts.get(kind="source_code").metadata["entry_point"] == "train.py"
    assert storage.read(build.version.artifacts.get(kind="reference_data").uri) == b"x\n1\n"


def test_monitor_reference_and_version_cannot_be_changed(project):
    deployment = running(project)
    monitor = DriftMonitor.objects.create(
        version=deployment.version, name="immutable", reference_uri="s3://test/original.csv"
    )
    client = APIClient()
    client.force_authenticate(project.owner)
    response = client.patch(
        f"/api/drift-monitors/{monitor.public_id}/", {"version": str(deployment.version.public_id)}, format="json"
    )
    assert response.status_code == 400
    monitor.refresh_from_db()
    assert monitor.reference_uri == "s3://test/original.csv"


def test_api_lifecycle_preview_build_register_deploy(project, monkeypatch, django_capture_on_commit_callbacks):
    """Real API/ORM lifecycle; replace only infrastructure and task dispatch."""
    from apps.deployment.tasks import execute_deployment, register_build

    storage = MemoryStorage()
    storage.presigned_get = lambda uri, expires: f"https://storage.test/{uri}"
    monkeypatch.setattr("apps.catalog.services.preview.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.catalog.api.serializers.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.deployment.services.builds.S3Storage", lambda: storage)
    monkeypatch.setattr("apps.registry.services.versions.S3Storage", lambda: storage)
    registry = SimpleNamespace(promote=lambda **kwargs: ("published", "sha256:published"))
    monkeypatch.setattr("apps.registry.services.versions.image_registry_for", lambda build: registry)
    monkeypatch.setattr("apps.observability.services.outbox._publish_pending", lambda: None)
    monkeypatch.setattr("apps.deployment.tasks.invalidate_model_server_cache", lambda *args: None)
    monkeypatch.setattr("apps.deployment.tasks.append_deployment_log", lambda *args: None)
    monkeypatch.setattr("apps.deployment.tasks.reset_deployment_logs", lambda *args: None)
    monkeypatch.setattr("apps.deployment.tasks.execute_build.delay", lambda id: SimpleNamespace(id="build-task"))
    monkeypatch.setattr("apps.deployment.tasks.register_build.delay", lambda id: register_build(id))
    monkeypatch.setattr("apps.deployment.tasks.execute_deployment.delay", lambda id: SimpleNamespace(id="deploy-task"))
    client = APIClient()
    client.force_authenticate(project.owner)
    upload = client.post(
        "/api/models/preview/upload-urls/",
        {"name": "API lifecycle", "flavor": "xgboost", "files": [
            {"kind": "source_artifact", "filename": "model.pkl", "size_bytes": 1024},
            {"kind": "reference_data", "filename": "reference.csv", "size_bytes": 2048},
        ]},
        format="json",
    )
    assert upload.status_code == 200, upload.data
    payloads = {"source_artifact": b"model", "reference_data": b"x\n1\n"}
    assets = []
    for item in upload.data["files"]:
        storage.objects[item["s3_uri"]] = payloads[item["kind"]]
        assets.append({"kind": item["kind"], "name": item["filename"], "s3_uri": item["s3_uri"]})
    created = client.post(
        "/api/models/",
        {
            "name": "API lifecycle",
            "flavor": "xgboost",
            "project_id": upload.data["project_id"],
            "assets": assets,
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    id = created.data["id"]
    built = client.post(f"/api/models/{id}/builds/", {"revision": created.data["preview_revision"]}, format="json")
    assert built.status_code == 201, built.data
    build = Build.objects.get(public_id=built.data["id"])
    assert client.post("/api/deployments/", {"build": str(build.public_id)}, format="json").status_code == 400
    complete_build(build, image_uri="temporary")
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(f"/api/builds/{build.public_id}/register/")
    assert response.status_code == 202, response.data
    build.refresh_from_db()
    assert build.version_id
    deployed = client.post("/api/deployments/", {"build": str(build.public_id)}, format="json")
    assert deployed.status_code == 201, deployed.data

    def ready(deployment):
        return Endpoint.objects.create(deployment=deployment, public_url="http://runtime.test", health_status="healthy")

    monkeypatch.setattr("apps.deployment.tasks.deployment_backend", lambda backend: SimpleNamespace(deploy=ready))
    execute_deployment(deployed.data["id"])
    from apps.deployment.models import Deployment
    from apps.deployment.services.local_execution import check_execution
    import uuid
    from datetime import timedelta
    from django.utils import timezone
    from unittest.mock import Mock

    candidate = Deployment.objects.get(public_id=deployed.data["id"])
    token = uuid.uuid4()
    Deployment.objects.filter(pk=candidate.pk).update(
        execution_check_token=token, execution_check_lease_until=timezone.now() + timedelta(seconds=30),
    )
    assert check_execution("deploy", str(candidate.public_id), str(token),
        inspector=Mock(return_value=Mock(attrs={"State": {"Status": "running"}})),
        remover=Mock(), probe=Mock(check=Mock(return_value="healthy"))) == "succeeded"
    overview = client.get(f"/api/models/{id}/")
    assert overview.data["lifecycle_status"] == "running"
    assert overview.data["active_endpoint"]["version_id"] == str(build.version.public_id)
    assert overview.data["reference_data"]["name"] == "reference.csv"


def test_training_retry_preserves_frozen_inputs_not_updated_workspace(project, monkeypatch):
    from apps.catalog.models import WorkspaceAsset
    from apps.training.models import TrainingJob
    from apps.training.services.jobs import retry_job

    storage = MemoryStorage()
    inputs = {}
    for kind, name, content in (
        ("code", "code.zip", b"old code"),
        ("data", "data.zip", b"old data"),
    ):
        inputs[kind] = storage.put(f"original/{name}", SimpleUploadedFile(name, content), "application/octet-stream")
    job = TrainingJob.objects.create(
        project=project,
        name="retry",
        status="failed",
        model_flavor="xgboost",
        code_snapshot_uri=inputs["code"].uri,
        data_snapshot_uri=inputs["data"].uri,
    )
    WorkspaceAsset.objects.create(
        project=project, kind="data", relative_path="data.zip", s3_uri="s3://test-bucket/new-workspace.zip"
    )
    monkeypatch.setattr("apps.observability.services.outbox._publish_pending", lambda: None)
    retry = retry_job(job, storage=storage)
    assert retry.status == "queued"
    assert retry.retry_of_id == job.pk
    for field, kind in (
        ("code_snapshot_uri", "code"),
        ("data_snapshot_uri", "data"),
    ):
        assert str(retry.public_id) in getattr(retry, field)
        assert storage.read(getattr(retry, field)) == storage.read(inputs[kind].uri)
    assert job.status == "failed"


@pytest.mark.parametrize("path", ["../outside.csv", "/absolute.csv", "data\\outside.csv"])
def test_workspace_rejects_unsafe_paths(project, path):
    from apps.catalog.services.workspace import save_workspace_file

    storage = MemoryStorage()
    with pytest.raises(ValidationError):
        save_workspace_file(
            project=project,
            kind="data",
            relative_path=path,
            uploaded_file=SimpleUploadedFile("data.csv", b"x\n1\n"),
            storage=storage,
        )
    assert storage.objects == {}


@pytest.mark.parametrize("state", ["deleting", "delete_failed"])
def test_drift_callback_cannot_complete_run_during_project_cleanup(project, settings, state):
    from apps.drift.models import DriftRun

    deployment = running(project)
    monitor = DriftMonitor.objects.create(version=deployment.version, name="cleanup", reference_uri="s3://test/ref.csv")
    run = DriftRun.objects.create(monitor=monitor, status="running")
    project.deletion_state = state
    project.save()
    settings.CONTROL_PLANE_WEBHOOK_SECRET = "test-internal-callback-secret"
    client = APIClient()
    response = client.post(
        f"/internal/webhooks/drift-runs/{run.public_id}/",
        {"summary": {"has_drift": True}},
        format="json",
        HTTP_X_CONTROL_PLANE_SECRET=settings.CONTROL_PLANE_WEBHOOK_SECRET,
    )
    assert response.status_code == 200
    run.refresh_from_db()
    assert run.status == "running"
    run.delete()
    response = client.post(
        f"/internal/webhooks/drift-runs/{run.public_id}/",
        {},
        format="json",
        HTTP_X_CONTROL_PLANE_SECRET=settings.CONTROL_PLANE_WEBHOOK_SECRET,
    )
    assert response.status_code == 200
    assert response.data["status"] == "deleted"
