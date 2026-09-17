import io
import subprocess
import threading
import pytest

from src import application as runner
from unittest.mock import Mock

def test_read_int_file(tmp_path):
    value = tmp_path / "value"
    value.write_text("42", encoding="utf-8")
    assert runner._read_int_file(str(value)) == 42
    value.write_text("max", encoding="utf-8")
    assert runner._read_int_file(str(value)) is None
    value.write_text("invalid", encoding="utf-8")
    assert runner._read_int_file(str(value)) is None
    assert runner._read_int_file(str(tmp_path / "missing")) is None


def test_cgroup_memory(monkeypatch):
    values = {
        "/sys/fs/cgroup/memory.current": 50 * 1024 * 1024,
        "/sys/fs/cgroup/memory.max": 100 * 1024 * 1024,
    }
    monkeypatch.setattr(runner, "_read_int_file", lambda path: values.get(path))
    assert runner._read_cgroup_memory() == (50.0, 100.0, 50.0)


def test_gpu_metrics_unavailable_and_aggregated(monkeypatch):
    monkeypatch.setattr(runner.subprocess, "run", Mock(side_effect=FileNotFoundError))
    assert runner._read_gpu_metrics()["gpu_available"] is False
    result = subprocess.CompletedProcess([], 0, "10, 100, 400\n80, 200, 600\n", "")
    monkeypatch.setattr(runner.subprocess, "run", Mock(return_value=result))
    metrics = runner._read_gpu_metrics()
    assert metrics["gpu_available"] is True
    assert metrics["gpu_percent"] == 80.0
    assert metrics["gpu_memory_percent"] == 30.0


def test_metric_emitter_emits_one_sample(monkeypatch):
    stop = threading.Event()
    payloads = []
    monkeypatch.setattr(runner, "_read_cgroup_cpu_limit", lambda: 2.0)
    usage = iter((1.0, 2.0))
    monkeypatch.setattr(runner, "_read_cgroup_cpu_usage_seconds", lambda: next(usage))
    times = iter((10.0, 11.0))
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(runner, "_read_cgroup_memory", lambda: (10.0, 20.0, 50.0))
    monkeypatch.setattr(runner, "_read_gpu_metrics", lambda: {"gpu_available": False})
    monkeypatch.setattr(runner, "metric_log", lambda payload: (payloads.append(payload), stop.set()))
    thread = runner.start_metric_emitter(stop, interval_seconds=0)
    thread.join(timeout=1)
    assert payloads[0]["cpu_percent"] == 50.0
    assert payloads[0]["memory_percent"] == 50.0


class FakeProcess:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.stdout = io.StringIO("out one\nout two\n")
        self.stderr = io.StringIO("warning\n")

    def wait(self):
        return self.returncode


def test_run_training_validates_entry_point(runner_workspace):
    with pytest.raises(RuntimeError, match="entry point"):
        runner.run_training("missing.py", "v1")


def test_run_training_streams_output_and_sets_environment(monkeypatch, runner_workspace):
    source_dir = runner_workspace["SOURCE_DIR"]
    (source_dir / "train.py").write_text("pass", encoding="utf-8")
    captured = {}
    monkeypatch.setenv("TENANT_ID", "tenant-1")
    monkeypatch.setenv("S3_OUTPUT_UPLOAD_CAPABILITY", "must-not-leak")
    monkeypatch.setattr(runner, "start_metric_emitter", lambda event: Mock())
    monkeypatch.setattr(runner, "log_to_redis", Mock())

    def popen(*args, **kwargs):
        captured.update(kwargs)
        return FakeProcess(3)

    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    result = runner.run_training("train.py", "v2")
    assert result.returncode == 3
    assert result.stdout == "out one\nout two\n"
    assert result.stderr == "warning\n"
    assert captured["env"]["MODEL_VERSION"] == "v2"
    assert "MLFLOW_EXPERIMENT_NAME" not in captured["env"]
    assert "S3_OUTPUT_UPLOAD_CAPABILITY" not in captured["env"]
    assert "TENANT_ID" not in captured["env"]


def _main_env(monkeypatch):
    monkeypatch.setenv("S3_SOURCE_URI", "https://example.test/source")
    monkeypatch.setenv("S3_TRAINING_DATA_URI", "https://example.test/train")
    monkeypatch.setenv("S3_OUTPUT_UPLOAD_URL", "https://control-plane.test/output-url")
    monkeypatch.setenv("S3_OUTPUT_UPLOAD_CAPABILITY", "output-capability")
    monkeypatch.setenv("ENTRY_POINT", "custom.py")
    monkeypatch.setenv("MODEL_VERSION", "v3")
    monkeypatch.setenv("TRAINING_JOB_ID", "job-3")


def test_main_orchestrates_success(monkeypatch, runner_workspace):
    _main_env(monkeypatch)
    monkeypatch.setenv("REQUIREMENTS_TEXT", "cHl0ZXN0PT04LjIuMg==")
    downloads = Mock()
    extract = Mock()
    install = Mock()
    bundle = Mock()
    archive = Mock()
    upload = Mock()
    monkeypatch.setattr(runner, "download_presigned_url", downloads)
    monkeypatch.setattr(runner, "safe_extract_zip", extract)
    monkeypatch.setattr(runner, "install_requirements", install)
    monkeypatch.setattr(runner, "run_training", Mock(return_value=subprocess.CompletedProcess([], 0, "ok", "")))
    monkeypatch.setattr(runner, "write_mlops_bundle", bundle)
    monkeypatch.setattr(runner, "create_model_archive", archive)
    request_upload_url = Mock(return_value="https://example.test/output")
    monkeypatch.setattr(runner, "request_output_upload_url", request_upload_url)
    monkeypatch.setattr(runner, "upload_presigned_url", upload)
    runner.main()
    assert downloads.call_count == 2
    assert (runner.SOURCE_DIR / "requirements.txt").read_text(encoding="utf-8") == "pytest==8.2.2"
    extract.assert_called_once()
    install.assert_called_once()
    bundle.assert_called_once_with(
        entry_point="custom.py",
        model_version="v3",
        training_job_id="job-3",
        status="succeeded",
        stdout_text="ok",
        stderr_text="",
    )
    archive.assert_called_once()
    request_upload_url.assert_called_once_with(
        "https://control-plane.test/output-url",
        "output-capability",
    )
    upload.assert_called_once()


def test_main_writes_plain_requirements_and_stops_after_failed_training(monkeypatch, runner_workspace):
    _main_env(monkeypatch)
    monkeypatch.setenv("REQUIREMENTS_TEXT", "numpy pandas")
    monkeypatch.setattr(runner, "download_presigned_url", Mock())
    monkeypatch.setattr(runner, "safe_extract_zip", Mock())
    monkeypatch.setattr(runner, "install_requirements", Mock())
    monkeypatch.setattr(runner, "run_training", Mock(return_value=subprocess.CompletedProcess([], 7, "", "bad")))
    bundle = Mock()
    monkeypatch.setattr(runner, "write_mlops_bundle", bundle)
    monkeypatch.setattr(runner, "create_model_archive", Mock())
    with pytest.raises(RuntimeError, match="exit code 7"):
        runner.main()
    assert (runner.SOURCE_DIR / "requirements.txt").read_text(encoding="utf-8") == "numpy\npandas"
    assert bundle.call_args.kwargs["status"] == "failed"
    runner.create_model_archive.assert_not_called()
