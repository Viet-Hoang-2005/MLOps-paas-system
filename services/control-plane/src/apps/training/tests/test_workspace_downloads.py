from io import BytesIO
from zipfile import ZipFile, ZipInfo

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.tests.test_preview_lifecycle import MemoryStorage
from apps.training.models import TrainingJob, TrainingJobEntry, TrainingOutput
from apps.training.services import downloads
from apps.training.services.storage_scope import expected_training_uris, training_prefix_for

pytestmark = pytest.mark.django_db


class Storage(MemoryStorage):
    def open_stream(self, uri):
        data = self.objects[uri]
        return BytesIO(data), len(data), "application/octet-stream"


@pytest.fixture
def files(monkeypatch):
    owner = get_user_model().objects.create_user("downloads@example.test", "password")
    job = TrainingJob.objects.create(owner=owner, storage_layout="tenant")
    storage = Storage()
    for path, payload in [("train.py", b"print(1)\r\n"), ("data/a.csv", b"a,b\r\n1,2\r\n"),
                          ("database/other.csv", b"x\n1\n"), ("zero.md", b"")]:
        stored = storage.put(f"{training_prefix_for(job)}/draft/objects/{path}", payload)
        TrainingJobEntry.objects.create(job=job, relative_path=path, kind="script" if path.endswith(".py") else "document",
            s3_uri=stored.uri, checksum=stored.checksum, size_bytes=stored.size_bytes)
    for path in ["data", "data/empty", "empty"]:
        TrainingJobEntry.objects.create(job=job, relative_path=path, kind="folder")
    for path, payload in [("model.pkl", b"\x00\xff\x80model"), ("reports/a.json", b'{"a":1}'),
                          ("reports/nested/b.bin", b"\xff\x00"), ("reports2/out.json", b"{}")]:
        stored = storage.put(f"{training_prefix_for(job)}/output/{path}", payload)
        TrainingOutput.objects.create(job=job, relative_path=path, kind="model" if path.endswith(".pkl") else "metric",
            s3_uri=stored.uri, checksum=stored.checksum, size_bytes=stored.size_bytes)
    monkeypatch.setattr(downloads, "S3Storage", lambda: storage)
    client = APIClient()
    client.force_authenticate(owner)
    return job, storage, client


def get(client, job, area, path=None, **params):
    return client.get(f"/api/training-jobs/{job.public_id}/{area}/download/", {**params, **({"path": path} if path is not None else {})})


def body(response):
    try:
        return b"".join(response.streaming_content)
    finally:
        response.close()


def freeze(job, storage):
    bundle = BytesIO()
    with ZipFile(bundle, "w") as archive:
        for entry in job.entries.all():
            archive.writestr(entry.relative_path + ("/" if entry.kind == "folder" else ""),
                b"" if entry.kind == "folder" else storage.objects[entry.s3_uri])
    job.code_snapshot_uri = expected_training_uris(job, storage.bucket)["code"]
    storage.objects[job.code_snapshot_uri] = bundle.getvalue()
    job.submitted_at = timezone.now()
    job.save()


@pytest.mark.parametrize("submitted", [False, True])
def test_input_selection_preserves_exact_file_and_folder_scope(files, submitted):
    job, storage, client = files
    if submitted:
        freeze(job, storage)
        # Snapshot downloads must not read mutable draft objects.
        storage.objects[job.entries.get(relative_path="train.py").s3_uri] = b"changed draft"
    response = get(client, job, "input", "train.py")
    assert response.status_code == 200
    assert response["Content-Disposition"] == 'attachment; filename="train.py"'
    assert body(response) == b"print(1)\r\n"
    response = get(client, job, "input", "data")
    assert response["Content-Disposition"] == 'attachment; filename="data.zip"'
    with ZipFile(BytesIO(body(response))) as archive:
        assert set(archive.namelist()) >= {"data/a.csv", "data/empty/"}
        assert not any(name.startswith("database/") for name in archive.namelist())
        assert archive.read("data/a.csv") == b"a,b\r\n1,2\r\n"
    response = get(client, job, "input")
    assert response["Content-Disposition"] == 'attachment; filename="input.zip"'
    with ZipFile(BytesIO(body(response))) as archive:
        assert "database/other.csv" in archive.namelist() and "empty/" in archive.namelist()
    assert body(get(client, job, "input", "zero.md")) == b""


def test_output_download_is_binary_safe_and_download_all_is_a_zip(files):
    job, _, client = files
    response = get(client, job, "outputs", "model.pkl")
    assert response.status_code == 200 and body(response) == b"\x00\xff\x80model"
    with ZipFile(BytesIO(body(get(client, job, "outputs", "reports")))) as archive:
        assert set(archive.namelist()) == {"reports/a.json", "reports/nested/b.bin"}
        assert archive.read("reports/nested/b.bin") == b"\xff\x00"
    with ZipFile(BytesIO(body(get(client, job, "outputs", "reports/nested")))) as archive:
        assert archive.namelist() == ["nested/b.bin"]
    with ZipFile(BytesIO(body(get(client, job, "outputs")))) as archive:
        assert len(archive.namelist()) == 4 and archive.read("model.pkl") == b"\x00\xff\x80model"


def test_empty_missing_invalid_and_stale_selections_are_rejected(files):
    job, _, client = files
    assert get(client, job, "input", "empty").status_code == 404
    assert get(client, job, "outputs", "absent").status_code == 404
    assert get(client, job, "input", "../outside").status_code == 400
    assert get(client, job, "input", revision=job.revision + 1).status_code == 409
    job.outputs.all().delete()
    assert get(client, job, "outputs").status_code == 404
    job.entries.exclude(kind="folder").delete()
    assert get(client, job, "input").status_code == 404


def test_downloads_are_owner_scoped_and_check_storage_scope(files):
    job, _, client = files
    other = get_user_model().objects.create_user("other-downloads@example.test", "password")
    client.force_authenticate(other)
    assert get(client, job, "input").status_code == 404
    assert get(client, job, "outputs").status_code == 404
    client.force_authenticate(job.owner)
    job.outputs.filter(relative_path="model.pkl").update(s3_uri="s3://test-bucket/users/other/model.pkl")
    assert get(client, job, "outputs", "model.pkl").status_code == 409
    job.outputs_purged_at = timezone.now()
    job.save()
    assert get(client, job, "outputs").status_code == 409


def test_copy_failure_closes_temporary_files(files, monkeypatch):
    job, storage, _ = files
    opened = []
    factory = downloads._temporary
    def temporary():
        stream = factory()
        opened.append(stream)
        return stream
    monkeypatch.setattr(downloads, "_temporary", temporary)
    monkeypatch.setattr(storage, "open_stream", lambda uri: (_ for _ in ()).throw(OSError("S3 unavailable")))
    with pytest.raises(OSError):
        downloads.workspace_download(job, area="output", storage=storage)
    assert opened and all(stream.closed for stream in opened)


def test_snapshot_scope_and_unsafe_archive_entries_are_rejected(files):
    job, storage, client = files
    freeze(job, storage)
    job.code_snapshot_uri = "s3://test-bucket/users/another-job/source.zip"
    job.save()
    assert get(client, job, "input", "train.py").status_code == 409
    job.code_snapshot_uri = expected_training_uris(job, storage.bucket)["code"]
    job.save()
    for info in [ZipInfo("../escape.py"), ZipInfo("train.py")]:
        if info.filename == "train.py":
            info.create_system = 3
            info.external_attr = 0o120777 << 16
        archive = BytesIO()
        with ZipFile(archive, "w") as bundle:
            bundle.writestr(info, b"outside")
        storage.objects[job.code_snapshot_uri] = archive.getvalue()
        assert get(client, job, "input").status_code == 400


def test_failed_integrity_and_size_checks_do_not_return_partial_downloads(files, monkeypatch):
    job, _, client = files
    job.entries.filter(relative_path="train.py").update(checksum="0" * 64)
    assert get(client, job, "input", "train.py").status_code == 409
    monkeypatch.setattr(downloads, "MAX_OUTPUT_DOWNLOAD", 2)
    assert get(client, job, "outputs").status_code == 400


def test_cross_origin_download_exposes_attachment_filename(files):
    job, _, client = files
    response = client.get(f"/api/training-jobs/{job.public_id}/input/download/", {"path": "train.py"},
        HTTP_ORIGIN="http://localhost:5173")
    assert response.status_code == 200
    assert "content-disposition" in response["Access-Control-Expose-Headers"].lower()
    response.close()
