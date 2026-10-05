import uuid
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.deployment.models import Build, Deployment
from apps.drift.models import DriftMonitor
from apps.drift.services.monitors import create_monitor, validate_reference_upload
from common.api.exceptions import Conflict


@pytest.fixture
def running_version(db):
    owner = get_user_model().objects.create_user("monitor-reference@example.test", "test-password")
    project = ModelProject.objects.create(owner=owner, name="Monitor reference")
    version = project.versions.create(version="1")
    build = Build.objects.create(project=project, version=version, status="ready")
    deployment = Deployment.objects.create(version=version, build=build, status="succeeded")
    project.active_deployment = deployment
    project.save(update_fields=["active_deployment"])
    return version


def create(version, storage, name="default", upload=True):
    data = {"version": version, "name": name}
    if upload:
        data["reference_file"] = SimpleUploadedFile("baseline.csv", b"feature,label\n1,safe\n")
    return create_monitor(data=data, backend="docker", storage=storage)


def test_upload_registers_once_and_subsequent_monitors_copy_same_reference(running_version):
    storage = MemoryStorage()
    first = create(running_version, storage)
    artifact = running_version.artifacts.get(kind="reference_data")
    assert f"/versions/{running_version.public_id}/" in artifact.uri
    assert artifact.checksum and artifact.size_bytes == len(b"feature,label\n1,safe\n")
    assert storage.read(artifact.uri) == storage.read(first.reference_uri)
    assert first.reference_uri != artifact.uri
    second = create(running_version, storage, name="second", upload=False)
    assert storage.read(second.reference_uri) == storage.read(artifact.uri)
    assert second.reference_uri != first.reference_uri
    assert running_version.artifacts.filter(kind="reference_data").count() == 1
    assert not running_version.project.preview.assets.exists()
    with pytest.raises(Conflict, match="already has reference"):
        create(running_version, storage, name="replacement")
    assert len(storage.objects) == 3


def test_failed_snapshot_copy_rolls_back_version_artifact_and_removes_upload(running_version):
    storage = MemoryStorage()
    storage.fail_copy = True
    with pytest.raises(RuntimeError):
        create(running_version, storage)
    assert not running_version.artifacts.exists()
    assert not DriftMonitor.objects.exists()
    assert storage.objects == {}
    assert len(storage.deleted) == 1


def test_monitor_insert_failure_cleans_only_new_objects(running_version, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.drift.services.monitors.DriftMonitor.objects.create", Mock(side_effect=RuntimeError("DB failed")))
    with pytest.raises(RuntimeError):
        create(running_version, storage)
    assert not running_version.artifacts.exists()
    assert storage.objects == {}
    assert len(storage.deleted) == 2


def test_missing_reference_and_changed_running_rejected(running_version):
    storage = MemoryStorage()
    with pytest.raises(ValidationError):
        create(running_version, storage, upload=False)
    project = running_version.project
    project.active_deployment.status = "stopped"
    project.active_deployment.save(update_fields=["status"])
    with pytest.raises(Conflict, match="Running"):
        create(running_version, storage)
    assert storage.objects == {}


@pytest.mark.parametrize("filename,content", [
    ("reference.json", b"a\n1\n"), ("empty.csv", b""), ("header.csv", b"a\n"),
    ("broken.csv", b"a,b\n1\n"), ("duplicate.csv", b"a,a\n1,2\n"),
    ("blank.csv", b"a,\n1,2\n"), ("invalid.csv", b"\xff\xfe"), ("nul.csv", b"a\n\x00\n"),
    ("large.csv", b"a" * (10 * 1024 * 1024 + 1)),
], ids=["extension", "empty", "header-only", "width", "duplicate-header", "blank-header", "encoding", "nul", "oversize"])
def test_invalid_csv_rejected_and_stream_rewound(filename, content):
    upload = SimpleUploadedFile(filename, content)
    with pytest.raises(ValidationError):
        validate_reference_upload(upload)
    assert upload.tell() == 0


def test_reference_endpoints_enforce_tenant_and_existing_reference(running_version, monkeypatch):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.drift.services.monitors.S3Storage", lambda: storage)
    client = APIClient()
    client.force_authenticate(running_version.project.owner)
    url = "/api/drift-monitors/"
    payload = {"version": str(running_version.public_id), "name": "default", "trigger_threshold": 1000,
               "reference_file": SimpleUploadedFile("reference.csv", b"x\n1\n")}
    response = client.post(url, payload, format="multipart")
    assert response.status_code == 201
    monitor_id = response.data["id"]
    reference_url = f"/api/drift-monitors/{monitor_id}/reference-url/"
    monkeypatch.setattr("apps.drift.services.monitors.S3Storage", lambda: Mock(presigned_get=lambda uri, expires: "https://s3.example/reference"))
    assert client.get(reference_url).data == {"url": "https://s3.example/reference"}
    other = get_user_model().objects.create_user("other-reference@example.test", "test-password")
    client.force_authenticate(other)
    assert client.get(reference_url).status_code == 404
    payload["reference_file"] = SimpleUploadedFile("reference.csv", b"x\n2\n")
    assert client.post(url, payload, format="multipart").status_code == 400
    client.force_authenticate(running_version.project.owner)
    payload.update(name="replace", reference_file=SimpleUploadedFile("replacement.csv", b"x\n2\n"))
    assert client.post(url, payload, format="multipart").status_code == 409
    payload.update(name="zero", trigger_threshold=0)
    assert client.post(url, payload, format="multipart").status_code == 400
    response = client.patch(f"/api/drift-monitors/{monitor_id}/", {"reference_file": SimpleUploadedFile("replace.csv", b"x\n2\n")}, format="multipart")
    assert response.status_code == 400
    assert client.get(f"/api/drift-monitors/{uuid.uuid4()}/reference-url/").status_code == 404
