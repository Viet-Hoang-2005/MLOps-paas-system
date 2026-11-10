import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.training.models import TrainingWorkspace, TrainingWorkspaceSecret
from apps.training.services import workspaces


@pytest.fixture
def setup_workspace(db, monkeypatch, settings):
    storage = MemoryStorage()
    monkeypatch.setattr(workspaces, "S3Storage", lambda: storage)
    settings.TRAINING_SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()
    owner = get_user_model().objects.create_user("draft-owner@example.com", "password123")
    other = get_user_model().objects.create_user("draft-other@example.com", "password123")
    client = APIClient()
    client.force_authenticate(owner)
    workspace = TrainingWorkspace.objects.create(owner=owner)
    return client, workspace, other, storage


def test_workspace_and_secrets_are_scoped_and_write_only(setup_workspace):
    client, workspace, other, _ = setup_workspace
    url = f"/api/training-workspaces/{workspace.public_id}/"
    response = client.put(url + "secrets/API_TOKEN/", {"revision": 1, "value": "example-private-value"}, format="json")
    assert response.status_code == 200
    assert "example-private-value" not in str(response.data)
    secret = TrainingWorkspaceSecret.objects.get(workspace=workspace, name="API_TOKEN")
    assert b"example-private-value" not in bytes(secret.ciphertext)
    detail = client.get(url)
    assert detail.status_code == 200
    assert detail.data["secrets"][0]["name"] == "API_TOKEN"
    assert "example-private-value" not in str(detail.data)
    client.force_authenticate(other)
    assert client.get(url).status_code == 404
    assert client.put(url + "secrets/API_TOKEN/", {"revision": 2, "value": "replacement"}, format="json").status_code == 404


def test_workspace_is_identified_by_uuid_without_a_name(setup_workspace):
    import uuid
    client, _, _, _ = setup_workspace
    response = client.post("/api/training-workspaces/", {}, format="json")
    assert response.status_code == 201
    workspace_id = response.data["id"]
    assert str(uuid.UUID(workspace_id)) == workspace_id
    assert "name" not in response.data
    workspace = TrainingWorkspace.objects.get(public_id=workspace_id)
    assert str(workspace) == workspace_id
    assert "name" not in client.get(f"/api/training-workspaces/{workspace_id}/").data
    assert all("name" not in row for row in client.get("/api/training-workspaces/").data)


def test_requirements_file_is_unique_and_cannot_be_replaced(setup_workspace):
    client, workspace, _, _ = setup_workspace
    url = f"/api/training-workspaces/{workspace.public_id}/"
    response = client.post(url + "entries/", {"revision": 1, "kind": "requirements", "path": "requirements.txt"}, format="json")
    assert response.status_code == 201
    entry = response.data["entry"]["id"]
    duplicate = client.post(url + "entries/", {"revision": 2, "kind": "requirements", "path": "requirements.txt"}, format="json")
    assert duplicate.status_code == 409
    nested = client.post(url + "entries/", {"revision": 2, "kind": "document", "path": "folder/requirements.txt"}, format="json")
    assert nested.status_code == 400
    moved = client.patch(url + f"entries/{entry}/", {"revision": 2, "path": "renamed.txt"}, format="json")
    assert moved.status_code == 400
    saved = client.patch(url + f"entries/{entry}/", {"revision": 2, "content": "numpy==1.26.4\n"}, format="json")
    assert saved.status_code == 200
    stale = client.patch(url + f"entries/{entry}/", {"revision": 2, "content": "different"}, format="json")
    assert stale.status_code == 409
    assert client.delete(url + f"entries/{entry}/", {"revision": 3}, format="json").status_code == 200
    assert client.post(url + "entries/", {"revision": 4, "kind": "requirements", "path": "requirements.txt"}, format="json").status_code == 201


def test_folder_move_updates_entry_point_and_rejects_collision(setup_workspace):
    client, workspace, _, _ = setup_workspace
    url = f"/api/training-workspaces/{workspace.public_id}/"
    folder = client.post(url + "entries/", {"revision": 1, "kind": "folder", "path": "scripts"}, format="json")
    assert folder.status_code == 201
    script = client.post(url + "entries/", {"revision": 2, "kind": "script", "path": "scripts/train.py", "content": "print(1)"}, format="json")
    assert script.status_code == 201
    assert client.patch(url, {"revision": 3, "entry_point": "scripts/train.py"}, format="json").status_code == 200
    moved = client.patch(url + f"entries/{folder.data['entry']['id']}/", {"revision": 4, "path": "src"}, format="json")
    assert moved.status_code == 200
    detail = client.get(url).data
    assert detail["entry_point"] == "src/train.py"
    assert {item["path"] for item in detail["entries"]} == {"src", "src/train.py"}
    assert client.post(url + "entries/", {"revision": 5, "kind": "script", "path": "src/train.py"}, format="json").status_code == 409


def test_secrets_fail_closed_without_a_key(setup_workspace, settings):
    client, workspace, _, _ = setup_workspace
    settings.TRAINING_SECRET_ENCRYPTION_KEY = ""
    url = f"/api/training-workspaces/{workspace.public_id}/"
    assert client.get(url).data["secrets_available"] is False
    assert client.put(url + "secrets/MY_TOKEN/", {"revision": 1, "value": "value"}, format="json").status_code == 503


def test_csv_requires_upload_and_requirements_replacement_is_rejected(setup_workspace):
    client, workspace, _, _ = setup_workspace
    url = f"/api/training-workspaces/{workspace.public_id}/entries/"
    response = client.post(url, {"revision": 1, "kind": "data", "path": "data.csv", "content": "x\n1\n"}, format="json")
    assert response.status_code == 400
    response = client.post(url, {"revision": "1", "kind": "data", "path": "data.csv",
                                  "file": SimpleUploadedFile("data.csv", b"x\n1\n")}, format="multipart")
    assert response.status_code == 201
    requirements = client.post(url, {"revision": 2, "kind": "requirements", "path": "requirements.txt"}, format="json")
    entry_id = requirements.data["entry"]["id"]
    replace = client.patch(url + f"{entry_id}/", {"revision": "3", "file": SimpleUploadedFile("requirements.txt", b"numpy\n")}, format="multipart")
    assert replace.status_code == 400


def test_file_edit_changes_path_type_and_content_atomically(setup_workspace):
    client, workspace, _, storage = setup_workspace
    url = f"/api/training-workspaces/{workspace.public_id}/"
    created = client.post(url + "entries/", {"revision": 1, "kind": "script", "path": "train.py", "content": "print(1)"}, format="json")
    entry_id = created.data["entry"]["id"]
    client.patch(url, {"revision": 2, "entry_point": "train.py"}, format="json")
    response = client.patch(url + f"entries/{entry_id}/", {"revision": 3, "path": "settings.json", "kind": "config", "content": '{"a": 1}'}, format="json")
    assert response.status_code == 200
    assert response.data["entry"]["path"] == "settings.json"
    assert client.get(url).data["entry_point"] == ""
    assert b'{"a": 1}' in storage.objects.values()
