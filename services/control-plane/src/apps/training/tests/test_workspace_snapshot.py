import hashlib
from io import BytesIO
from zipfile import ZipFile

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from apps.training.models import TrainingJob, TrainingJobEntry
from apps.training.services.workspaces import snapshot_input
from common.api.exceptions import Conflict


class FakeStorage:
    bucket = "training"

    def __init__(self, contents):
        self.contents = contents
        self.on_read = None

    def parse_uri(self, uri):
        bucket, key = uri.removeprefix("s3://").split("/", 1)
        return bucket, key

    def read(self, uri, max_bytes):
        if self.on_read:
            self.on_read()
        return self.contents[uri]


@pytest.fixture
def workspace_snapshot(db):
    user = get_user_model().objects.create_user("snapshot@example.test", "test-password")
    workspace = TrainingJob.objects.create(owner=user, entry_point="src/train.py")
    TrainingJobEntry.objects.create(job=workspace, relative_path="src", kind="folder")
    TrainingJobEntry.objects.create(job=workspace, relative_path="empty", kind="folder")
    payload = b"print('hello')\n"
    uri = f"s3://training/users/{user.tenant_id}/training/jobs/{workspace.public_id}/draft/objects/source"
    entry = TrainingJobEntry.objects.create(
        job=workspace, relative_path="src/train.py", kind="script", s3_uri=uri,
        checksum=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload),
    )
    return workspace, entry, FakeStorage({uri: payload})


@pytest.mark.django_db
def test_snapshot_preserves_paths_and_empty_folders(workspace_snapshot):
    workspace, _, storage = workspace_snapshot
    result = snapshot_input(workspace, revision=workspace.revision, storage=storage)
    with ZipFile(BytesIO(result["archive"])) as archive:
        assert set(archive.namelist()) == {"src/", "empty/", "src/train.py"}
        assert archive.read("src/train.py") == b"print('hello')\n"
    assert result["entry_point"] == "src/train.py"


@pytest.mark.django_db
def test_snapshot_rejects_changed_workspace(workspace_snapshot):
    workspace, _, storage = workspace_snapshot
    storage.on_read = lambda: TrainingJob.objects.filter(pk=workspace.pk).update(revision=2)
    with pytest.raises(Conflict):
        snapshot_input(workspace, revision=1, storage=storage)


@pytest.mark.django_db
def test_snapshot_rejects_wrong_storage_scope_and_corrupt_content(workspace_snapshot):
    workspace, entry, storage = workspace_snapshot
    entry.s3_uri = "s3://training/users/other/private"
    entry.save(update_fields=["s3_uri"])
    with pytest.raises(ValidationError, match="storage scope"):
        snapshot_input(workspace, revision=1, storage=storage)
    entry.s3_uri = next(iter(storage.contents))
    entry.checksum = "0" * 64
    entry.save(update_fields=["s3_uri", "checksum"])
    with pytest.raises(ValidationError, match="integrity"):
        snapshot_input(workspace, revision=1, storage=storage)
