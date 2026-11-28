from dataclasses import replace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.deployment.models import Build, Deployment
from apps.drift.models import DriftMonitor
from apps.training.tests.factories import training_job
from apps.training.workspace.models import TrainingWorkspace

pytestmark = pytest.mark.django_db
CSV = b'column,notes\r\n1,"first\nsecond"\r\n'


@pytest.fixture
def resources(monkeypatch):
    owner = get_user_model().objects.create_user("csv-owner@example.test")
    workspace = TrainingWorkspace.objects.create(owner=owner)
    project = ModelProject.objects.create(owner=owner, name="CSV project")
    version = project.versions.create(version="1")
    build = Build.objects.create(project=project, version=version, status="ready")
    project.active_deployment = Deployment.objects.create(version=version, build=build, status="succeeded")
    project.save(update_fields=["active_deployment"])
    job = training_job(project=project, status="completed", storage_layout="tenant")
    storage = MemoryStorage()
    put = storage.put
    storage.presigned_put = Mock(return_value="https://storage.test/signed")
    storage.put = Mock(side_effect=put)
    read = storage.read

    def conditional_read(uri, max_bytes, *, expected_etag=None):
        if uri not in storage.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        if expected_etag is not None:
            assert expected_etag == storage.head(uri).etag
        return read(uri, max_bytes)

    original_head = storage.head

    def head(uri):
        if uri not in storage.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return replace(original_head(uri), content_type="text/csv")

    storage.read = conditional_read
    storage.head = head
    for module in (
        "infrastructure.storage.staged_csv", "apps.training.workspace.editing", "apps.training.outputs.artifacts",
        "apps.registry.artifacts.supplemental", "apps.drift.monitors.reference",
    ):
        monkeypatch.setattr(f"{module}.S3Storage", lambda: storage)
    client = APIClient()
    client.force_authenticate(owner)
    return client, storage, workspace, job, version


def issue(client, storage, purpose, resource, *, revision=None, payload=CSV):
    metadata = {"filename": "reference.csv", "size_bytes": len(payload)}
    if revision is not None:
        metadata["revision"] = revision
    response = client.post(f"/api/csv-upload-urls/{purpose}/{resource.public_id}/", metadata, format="json")
    assert response.status_code == 200, response.data
    assert response["Cache-Control"] == "private, no-store"
    args, kwargs = storage.presigned_put.call_args
    uri = args[0]
    assert args[1:] == (900, "text/csv", len(payload))
    assert kwargs == {"public": True}
    assert "/staging/users/" in uri and f"/csv/{purpose}/{resource.public_id}/" in uri
    storage.objects[uri] = payload
    return response.data["upload_token"], uri


@pytest.mark.parametrize("purpose", ["workspace", "training-output", "version", "drift-monitor"])
def test_upload_token_commits_object_without_proxying_the_file(resources, purpose):
    client, storage, workspace, job, version = resources
    resource, revision = {
        "workspace": (workspace, workspace.revision),
        "training-output": (job, job.output_revision),
        "version": (version, None),
        "drift-monitor": (version, None),
    }[purpose]
    token, staged_uri = issue(client, storage, purpose, resource, revision=revision)
    payload = {"csv_upload_token": token}
    if purpose == "workspace":
        url = f"/api/training-workspaces/{workspace.public_id}/entries/"
        response = client.post(url, {**payload, "kind": "data", "path": "data.csv", "revision": revision})
        assert response.status_code == 201, response.data
        row = workspace.entries.get(relative_path="data.csv")
        uri = row.s3_uri
        assert storage.objects[uri] == CSV
        token, _ = issue(client, storage, purpose, workspace, revision=response.data["revision"], payload=b"a\n3\n")
        edited = client.patch(
            f"{url}{row.public_id}/",
            {"csv_upload_token": token, "revision": response.data["revision"]},
        )
        assert edited.status_code == 200, edited.data
        row.refresh_from_db()
        assert storage.objects[row.s3_uri] == b"a\n3\n"
    elif purpose == "training-output":
        response = client.patch(
            f"/api/training-jobs/{job.public_id}/model-output/", {**payload, "output_revision": revision}
        )
        uri = job.outputs.get(kind="reference_data").s3_uri
    elif purpose == "version":
        response = client.post(f"/api/registry/versions/{version.public_id}/supplemental-artifacts/", payload)
        uri = version.artifacts.get(kind="reference_data").uri
    else:
        response = client.post(
            "/api/drift-monitors/",
            {**payload, "version": str(version.public_id), "name": "default", "trigger_threshold": 100},
        )
        uri = version.artifacts.get(kind="reference_data").uri
        assert DriftMonitor.objects.get(version=version).reference_uri == uri
    assert response.status_code in {200, 201}, response.data
    assert "/staging/" not in uri
    if purpose != "workspace":
        assert storage.objects[uri] == CSV
    assert staged_uri not in storage.objects
    storage.put.assert_not_called()


def test_upload_scope_revision_and_content_are_checked(resources):
    client, storage, workspace, _job, version = resources
    token, uri = issue(client, storage, "version", version)
    assert client.post(
        "/api/drift-monitors/",
        {"csv_upload_token": token, "version": str(version.public_id), "name": "default", "trigger_threshold": 100},
    ).status_code == 400
    version_url = f"/api/registry/versions/{version.public_id}/supplemental-artifacts/"
    del storage.objects[uri]
    assert client.post(version_url, {"csv_upload_token": token}).status_code == 400
    token, _ = issue(client, storage, "version", version, payload=b"x,y\n1\n")
    assert client.post(version_url, {"csv_upload_token": token}).status_code == 400
    assert not version.artifacts.exists()

    token, _ = issue(client, storage, "workspace", workspace, revision=workspace.revision)
    workspace_url = f"/api/training-workspaces/{workspace.public_id}/entries/"
    assert client.post(
        workspace_url, {"csv_upload_token": token, "revision": workspace.revision + 1, "kind": "data", "path": "data.csv"},
    ).status_code == 400
    client.force_authenticate(get_user_model().objects.create_user("csv-other@example.test"))
    assert client.post(
        f"/api/csv-upload-urls/workspace/{workspace.public_id}/",
        {"filename": "data.csv", "size_bytes": 10, "revision": workspace.revision},
    ).status_code == 404
    assert not workspace.entries.exists()


def test_object_replaced_after_validation_cannot_be_promoted(resources, monkeypatch):
    client, storage, _workspace, _job, version = resources
    token, uri = issue(client, storage, "version", version)

    def replaced_during_copy(source_uri, *_args, expected_etag, **_kwargs):
        storage.objects[source_uri] = b"x\n9\n"
        assert storage.head(source_uri).etag != expected_etag
        raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "CopyObject")

    monkeypatch.setattr(storage, "copy", replaced_during_copy)
    response = client.post(
        f"/api/registry/versions/{version.public_id}/supplemental-artifacts/", {"csv_upload_token": token}
    )
    assert response.status_code == 400
    assert not version.artifacts.exists()
    assert set(storage.objects) == {uri}
