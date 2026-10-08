import stat
import subprocess
import tarfile
import types
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest
from src import application as runner
from src import io as io_module


def test_require_env(monkeypatch):
    monkeypatch.setenv("VALUE", " present ")
    assert runner.require_env("VALUE") == "present"
    monkeypatch.delenv("VALUE")
    with pytest.raises(RuntimeError, match="VALUE"):
        runner.require_env("VALUE")


def test_redis_logging_is_optional_and_failure_safe(monkeypatch):
    assert runner.log_to_redis("ignored") is False
    client = Mock()
    module = types.SimpleNamespace(from_url=Mock(return_value=client))
    monkeypatch.setattr(runner, "redis", module)
    monkeypatch.setenv("TRAINING_JOB_ID", "job-1")
    monkeypatch.setenv("REDIS_URL", "redis://redis.test:6379/1")
    assert runner.log_to_redis("hello") is True
    client.rpush.assert_called_once_with("training_logs:job-1", "hello")
    client.expire.assert_called_once()
    monkeypatch.setenv("LOG_STORAGE_BACKEND", "loki")
    assert runner.log_to_redis("skip-redis") is False
    assert client.rpush.call_count == 1
    monkeypatch.delenv("LOG_STORAGE_BACKEND")
    module.from_url.side_effect = RuntimeError("offline")
    assert runner.log_to_redis("safe") is False


def test_download_presigned_url(monkeypatch, tmp_path):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.iter_content.return_value = [b"one", b"two"]
    get = Mock(return_value=response)
    monkeypatch.setattr("requests.get", get)
    destination = tmp_path / "nested" / "file.zip"
    runner.download_presigned_url("https://example.test/file", destination)
    assert destination.read_bytes() == b"onetwo"
    response.raise_for_status.assert_called_once()
    get.assert_called_once_with("https://example.test/file", stream=True, timeout=300)


@pytest.mark.parametrize("status", [200, 201, 204])
def test_upload_presigned_url_success(monkeypatch, tmp_path, status):
    source = tmp_path / "model.tar.gz"
    source.write_bytes(b"model")
    put = Mock(return_value=Mock(status_code=status))
    monkeypatch.setattr("requests.put", put)
    runner.upload_presigned_url(source, "https://example.test/upload")
    assert put.call_args.kwargs["timeout"] == 300
    assert put.call_args.kwargs["headers"] == {"Content-Type": "application/gzip"}


def test_upload_presigned_url_failure(monkeypatch, tmp_path):
    source = tmp_path / "model.tar.gz"
    source.write_bytes(b"model")
    monkeypatch.setattr("requests.put", Mock(return_value=Mock(status_code=500, text="failed")))
    with pytest.raises(RuntimeError, match="HTTP status 500"):
        runner.upload_presigned_url(source, "https://example.test/upload")


def test_safe_extract_zip_accepts_files_and_rejects_traversal(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("project/train.py", "print('ok')")
    destination = tmp_path / "source"
    runner.safe_extract_zip(archive, destination)
    assert (destination / "project" / "train.py").exists()

    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as handle:
        handle.writestr("../source-escape/payload", "bad")
    with pytest.raises(RuntimeError, match="unsafe path"):
        runner.safe_extract_zip(unsafe, destination)


def test_safe_extract_zip_rejects_symlink(tmp_path):
    archive = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(info, "target")
    with pytest.raises(RuntimeError, match="unsafe path"):
        runner.safe_extract_zip(archive, tmp_path / "source")


def test_safe_extract_zip_rejects_too_many_entries(tmp_path):
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for index in range(5):
            handle.writestr(f"file-{index}.txt", "x")
    with pytest.raises(RuntimeError, match="too many entries"):
        io_module.safe_extract_zip(archive, tmp_path / "out", max_files=4)
    assert not list((tmp_path / "out").iterdir())


def test_safe_extract_zip_rejects_oversized_expansion(tmp_path):
    archive = tmp_path / "big.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("a.csv", "0" * 4096)
        handle.writestr("b.csv", "0" * 4096)
    with pytest.raises(RuntimeError, match="expands beyond"):
        io_module.safe_extract_zip(archive, tmp_path / "out", max_uncompressed_bytes=8000)
    assert not list((tmp_path / "out").iterdir())
    io_module.safe_extract_zip(archive, tmp_path / "ok", max_uncompressed_bytes=8192)
    assert (tmp_path / "ok" / "a.csv").stat().st_size == 4096


def test_safe_extract_zip_rejects_decompression_bomb(tmp_path, monkeypatch):
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("zeros.bin", bytes(1) * (2 * 1024 * 1024))
    monkeypatch.setattr(io_module, "RATIO_CHECK_MIN_BYTES", 1024 * 1024)
    with pytest.raises(RuntimeError, match="decompression bomb"):
        io_module.safe_extract_zip(archive, tmp_path / "out")
    assert not list((tmp_path / "out").iterdir())


def test_install_requirements_noop_success_and_failure(monkeypatch, tmp_path, runner_workspace):
    missing = tmp_path / "missing.txt"
    runner.install_requirements(missing)
    run = Mock(return_value=subprocess.CompletedProcess([], 0, "installed\n", "warning\n"))
    runtime_log = Mock()
    monkeypatch.setattr(runner.subprocess, "run", run)
    monkeypatch.setattr(runner, "runtime_log", runtime_log)
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pytest", encoding="utf-8")
    monkeypatch.setenv("CAPABILITY_TOKEN", "super-secret-token")
    runner.install_requirements(requirements)
    runtime_log.detail.assert_any_call("installed")
    runtime_log.detail.assert_any_call("warning")
    assert "CAPABILITY_TOKEN" not in run.call_args.kwargs["env"]
    assert "PATH" in run.call_args.kwargs["env"]
    run.return_value = subprocess.CompletedProcess([], 2, "", "bad")
    with pytest.raises(RuntimeError, match="exit code 2"):
        runner.install_requirements(requirements)


def test_install_requirements_rejects_unsafe_dependencies(tmp_path):
    req_file = tmp_path / "req.txt"
    req_file.write_text("-e .\n")
    with pytest.raises(RuntimeError, match="Disallowed pip option"):
        runner.install_requirements(req_file)

    req_file.write_text("git+https://github.com/evil/repo.git\n")
    with pytest.raises(RuntimeError, match="Remote URL"):
        runner.install_requirements(req_file)

    req_file.write_text("../secret_pkg\n")
    with pytest.raises(RuntimeError, match="Local path references"):
        runner.install_requirements(req_file)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("MLmodel", "model"),
        ("model.pkl", "model"),
        ("weights.pt", "checkpoint"),
        ("info.json", "metadata"),
        ("run.log", "log"),
        ("data.bin", "other"),
    ],
)
def test_artifact_kind(name, expected):
    assert runner.artifact_kind(Path(name)) == expected


def test_create_model_archive_requires_model_and_packages_metadata(runner_workspace, tmp_path):
    archive_path = tmp_path / "model.tar.gz"
    with pytest.raises(RuntimeError, match="does not contain"):
        runner.create_model_archive(archive_path)
    model_dir = runner_workspace["MODEL_DIR"]
    (model_dir / "model.pkl").write_bytes(b"model")
    (model_dir / "_mlops").mkdir()
    (model_dir / "_mlops" / "summary.json").write_text("{}", encoding="utf-8")
    runner.create_model_archive(archive_path)
    with tarfile.open(archive_path) as archive:
        assert set(archive.getnames()) == {"model.pkl", "_mlops/summary.json"}
