import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections
from PIL import Image
from rest_framework.test import APIClient

from apps.auth.services import avatars
from apps.auth.tasks import delete_avatar_object

pytestmark = pytest.mark.django_db(transaction=True)


def image(color="blue"):
    output = BytesIO()
    Image.new("RGB", (3, 3), color).save(output, format="PNG")
    return SimpleUploadedFile("avatar.png", output.getvalue(), content_type="image/png")


class Storage:
    def __init__(self):
        self.objects = {}
        self.deleted = []

    def save(self, key, upload):
        assert not connection.in_atomic_block, "Upload must not hold a database transaction."
        assert key not in self.objects
        self.objects[key] = upload.read()
        return key

    def delete(self, key):
        assert not connection.in_atomic_block, "Cleanup must run after commit."
        self.deleted.append(key)
        self.objects.pop(key, None)


@pytest.fixture
def account(monkeypatch):
    owner = get_user_model().objects.create_user("avatar@example.test", "test-password")
    storage = Storage()
    monkeypatch.setattr(avatars, "avatar_storage", lambda: storage)
    monkeypatch.setattr(delete_avatar_object, "delay", lambda tenant, key: avatars.cleanup_avatar(tenant, key))
    client = APIClient()
    client.force_authenticate(owner)
    return owner, storage, client


def test_replace_and_remove_keep_one_current_object(account):
    owner, storage, client = account
    assert client.put("/api/auth/profile/", {"avatar": image()}, format="multipart").status_code == 200
    owner.refresh_from_db()
    first = owner.avatar.name
    assert client.put("/api/auth/profile/", {"avatar": image("red")}, format="multipart").status_code == 200
    owner.refresh_from_db()
    assert owner.avatar.name != first and first in storage.deleted
    assert list(storage.objects) == [owner.avatar.name]
    assert client.get("/api/auth/profile/").data["avatar"]
    assert client.put("/api/auth/profile/", {"remove_avatar": True}, format="json").status_code == 200
    owner.refresh_from_db()
    assert client.get("/api/auth/profile/").data["avatar"] is None
    assert not storage.objects


@pytest.mark.parametrize("kind", ["invalid", "oversized", "conflicting"])
def test_invalid_avatar_does_not_change_profile(account, kind):
    owner, storage, client = account
    payload = {"full_name": "Must not persist", "avatar": image()}
    if kind == "invalid":
        payload["avatar"] = SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")
    elif kind == "oversized":
        payload["avatar"] = SimpleUploadedFile("large.png", b"x" * (avatars.MAX_AVATAR_BYTES + 1), content_type="image/png")
    else:
        payload["remove_avatar"] = "true"
    assert client.put("/api/auth/profile/", payload, format="multipart").status_code == 400
    owner.refresh_from_db()
    assert owner.full_name == "" and not owner.avatar and not storage.objects


def test_database_failure_preserves_old_avatar_and_removes_upload(account, monkeypatch):
    owner, storage, _ = account
    owner = avatars.update_profile(owner, avatar=image())
    previous = owner.avatar.name
    monkeypatch.setattr(get_user_model(), "save", Mock(side_effect=RuntimeError("database failed")))
    with pytest.raises(RuntimeError):
        avatars.update_profile(owner, avatar=image("red"))
    owner.refresh_from_db()
    assert owner.avatar.name == previous
    assert list(storage.objects) == [previous]


def test_upload_response_loss_cleans_only_new_object(account):
    owner, storage, _ = account
    owner = avatars.update_profile(owner, avatar=image())
    previous = owner.avatar.name
    save = storage.save
    def broken(*args):
        save(*args)
        raise OSError("Upload response lost")
    storage.save = broken
    with pytest.raises(OSError):
        avatars.update_profile(owner, avatar=image("red"))
    owner.refresh_from_db()
    assert owner.avatar.name == previous and list(storage.objects) == [previous]


def test_cleanup_rejects_other_accounts_and_skips_current_avatar(account):
    owner, storage, _ = account
    owner = avatars.update_profile(owner, avatar=image())
    avatars.cleanup_avatar(owner.tenant_id, owner.avatar.name)
    with pytest.raises(ValueError):
        avatars.cleanup_avatar(f"T-{uuid.uuid4()}", owner.avatar.name)
    with pytest.raises(ValueError):
        avatars.cleanup_avatar(owner.tenant_id, f"users/{owner.tenant_id}/avatar/nested/../avatar.png")
    assert list(storage.objects) == [owner.avatar.name] and storage.deleted == []


def test_cleanup_retries_storage_errors(account, monkeypatch):
    owner, _, _ = account
    monkeypatch.setattr(avatars, "cleanup_avatar", Mock(side_effect=OSError("S3 unavailable")))
    retry = Mock(side_effect=RuntimeError("retry scheduled"))
    monkeypatch.setattr(delete_avatar_object, "retry", retry)
    with pytest.raises(RuntimeError, match="retry scheduled"):
        delete_avatar_object.run(owner.tenant_id, f"users/{owner.tenant_id}/avatar/old.png")
    assert retry.call_count == 1 and delete_avatar_object.max_retries == 5


def test_cleanup_broker_and_storage_outage_does_not_fail_committed_update(account, monkeypatch):
    owner, storage, _ = account
    owner = avatars.update_profile(owner, avatar=image())
    previous = owner.avatar.name
    monkeypatch.setattr(delete_avatar_object, "delay", Mock(side_effect=ConnectionError("broker unavailable")))
    storage.delete = Mock(side_effect=OSError("S3 unavailable"))
    current = avatars.update_profile(owner, avatar=image("red"))
    owner.refresh_from_db()
    assert owner.avatar.name == current.avatar.name != previous


def test_history_routes_and_model_are_removed(account):
    _, _, client = account
    assert client.get("/api/auth/profile/avatars/").status_code == 404
    assert client.post(f"/api/auth/profile/avatars/{uuid.uuid4()}/select/").status_code == 404
    assert "identity_useravatar" not in connection.introspection.table_names()


def test_avatar_upload_requires_a_file_and_an_authenticated_account(account):
    owner, storage, client = account
    assert client.put("/api/auth/profile/", {"avatar": f"users/{owner.tenant_id}/avatar/key.png"}, format="json").status_code == 400
    client.force_authenticate(user=None)
    assert client.put("/api/auth/profile/", {"avatar": image()}, format="multipart").status_code == 401
    assert not storage.objects


def test_registration_rejects_invalid_image_before_consuming_token(account, monkeypatch):
    from apps.auth.api import registration_endpoints
    _, _, client = account
    client.force_authenticate(user=None)
    read = Mock(return_value={"email": "new-avatar@example.test"})
    monkeypatch.setattr(registration_endpoints, "read_token", read)
    response = client.post("/api/auth/register/complete/", {"registration_token": "test-token",
        "password": "Strong-avatar-password-842!", "avatar": SimpleUploadedFile("x.png", b"invalid")},
        format="multipart", HTTP_ORIGIN="http://localhost:5173", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert response.status_code == 400
    assert all(call.kwargs.get("consume") is False for call in read.call_args_list)
    assert not get_user_model().objects.filter(email="new-avatar@example.test").exists()


def test_registration_uses_the_single_avatar_service(account, monkeypatch):
    from apps.auth.api import registration_endpoints
    _, storage, client = account
    client.force_authenticate(user=None)
    monkeypatch.setattr(registration_endpoints, "read_token", Mock(return_value={"email": "new-avatar@example.test"}))
    response = client.post("/api/auth/register/complete/", {"registration_token": "test-token",
        "password": "Strong-avatar-password-842!", "avatar": image()}, format="multipart",
        HTTP_ORIGIN="http://localhost:5173", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert response.status_code == 201
    user = get_user_model().objects.get(email="new-avatar@example.test")
    assert list(storage.objects) == [user.avatar.name]


@pytest.mark.parametrize("remove", [False, True])
def test_postgres_concurrent_avatar_changes_keep_only_current_object(account, remove):
    if connection.vendor != "postgresql":
        pytest.skip("Row-lock concurrency requires disposable PostgreSQL.")
    owner, storage, _ = account
    owner = avatars.update_profile(owner, avatar=image())
    gate = Barrier(2)
    def change(index):
        try:
            user = get_user_model().objects.get(pk=owner.pk)
            gate.wait(timeout=10)
            return avatars.update_profile(user, remove=True) if remove and index == 1 else avatars.update_profile(user, avatar=image("red"))
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(change, [0, 1]))
    owner.refresh_from_db()
    assert set(storage.objects) == ({owner.avatar.name} if owner.avatar else set())
