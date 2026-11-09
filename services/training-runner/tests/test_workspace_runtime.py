import errno
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from src import application as runner


def test_workspace_runtime_refuses_writable_input(monkeypatch, runner_workspace):
    monkeypatch.setenv("INPUT_CONTRACT", "workspace")
    monkeypatch.setenv("PREPARED_INPUT_DIR", str(runner_workspace["SOURCE_DIR"]))
    monkeypatch.setattr(runner.os, "statvfs", lambda path: SimpleNamespace(f_flag=0), raising=False)
    monkeypatch.setattr(runner.os, "ST_RDONLY", 1, raising=False)
    with pytest.raises(RuntimeError, match="mounted read-only"):
        runner._run()


def test_secret_redaction_applies_to_captured_output_and_bundle(monkeypatch, runner_workspace):
    monkeypatch.setattr(runner, "SECRET_VALUES", ["synthetic-secret", "line-one\nline-two"])
    text = runner.redact_training_output("synthetic-secret\nline-one\nline-two\n")
    assert "synthetic-secret" not in text
    assert "line-one" not in text
    assert "line-two" not in text
    (runner_workspace["MODEL_DIR"] / "model.bin").write_bytes(b"model")
    runner.write_mlops_bundle(entry_point="train.py", model_version="", training_job_id="job", status="succeeded",
        stdout_text="synthetic-secret", stderr_text="line-one\nline-two")
    for filename in ("stdout.txt", "stderr.txt"):
        content = (runner_workspace["MODEL_DIR"] / "_mlops" / filename).read_text()
        assert "synthetic-secret" not in content
        assert "line-one" not in content


def test_invalid_model_tree_is_rejected_before_metadata_or_tracking(monkeypatch, runner_workspace):
    validate = Mock(side_effect=RuntimeError("Unsafe model tree"))
    monkeypatch.setattr(runner.execution, "validate_model_tree", validate)
    tracking = Mock()
    monkeypatch.setattr(runner, "log_to_mlflow", tracking)
    with pytest.raises(RuntimeError, match="Unsafe model tree"):
        runner.write_mlops_bundle(entry_point="train.py", model_version="", training_job_id="job",
            status="succeeded", stdout_text="", stderr_text="")
    assert not (runner_workspace["MODEL_DIR"] / "_mlops").exists()
    tracking.assert_not_called()
