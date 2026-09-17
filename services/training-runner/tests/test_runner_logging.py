import io
import json
import logging
import subprocess
from unittest.mock import Mock

import pytest
from src.logging_utils import RuntimeLog

from src import application as runner


@pytest.fixture
def log_capture(monkeypatch, caplog):
    logger = logging.Logger("training-log-test", level=logging.DEBUG)
    logger.addHandler(caplog.handler)
    writer = Mock(return_value=False)
    monkeypatch.setattr(runner, "runtime_log", RuntimeLog(logger, writer=writer))
    return writer, caplog


@pytest.mark.parametrize("delivered,level", [(True, logging.DEBUG), (False, logging.INFO)])
def test_detail_delivery_controls_container_level(log_capture, delivered, level):
    writer, caplog = log_capture
    writer.return_value = delivered
    runner.log("epoch completed")
    writer.assert_called_once_with("epoch completed")
    assert [record.levelno for record in caplog.records] == [level]


def test_no_redis_and_failed_redis_keep_sanitized_output_at_info(monkeypatch, caplog):
    logger = logging.Logger("training-fallback-test", level=logging.DEBUG)
    logger.addHandler(caplog.handler)
    monkeypatch.setattr(runner, "runtime_log", RuntimeLog(logger, writer=runner.log_to_redis))
    runner.log("epoch without Redis")
    monkeypatch.setenv("TRAINING_JOB_ID", "job-test")
    monkeypatch.setenv("REDIS_URL", "redis://unit")
    monkeypatch.setattr(runner.redis, "from_url", Mock(side_effect=RuntimeError("offline")))
    runner.log("download https://storage.test/model?X-Amz-Signature=fixture-signature")
    assert [record.levelno for record in caplog.records] == [logging.INFO, logging.INFO]
    assert "fixture-signature" not in caplog.text


def test_redis_writer_sanitizes_before_rpush(monkeypatch):
    monkeypatch.setenv("TRAINING_JOB_ID", "job-test")
    monkeypatch.setenv("REDIS_URL", "redis://unit")
    client = Mock()
    monkeypatch.setattr(runner.redis, "from_url", Mock(return_value=client))
    assert runner.log_to_redis("Authorization: Bearer fixture-bearer") is True
    assert "fixture-bearer" not in client.rpush.call_args.args[1]
    client.expire.side_effect = RuntimeError("offline")
    assert runner.log_to_redis("epoch") is False


def test_resource_metric_protocol_is_raw_once(log_capture, capsys):
    writer, caplog = log_capture
    payload = {"cpu_percent": 25, "memory_percent": 40}
    runner.metric_log(payload)
    expected = "METRIC_JSON " + json.dumps(payload, separators=(",", ":"))
    assert capsys.readouterr().out == expected + "\n"
    writer.assert_called_once_with(expected)
    assert not caplog.records


def test_training_stream_preserves_metric_input_and_sanitizes_display(
    monkeypatch, runner_workspace, log_capture, capsys
):
    writer, caplog = log_capture
    (runner.SOURCE_DIR / "train.py").write_text("pass", encoding="utf-8")
    metric = '  METRIC_JSON:{"accuracy":0.9,"url":"https://storage.test/a?X-Amz-Signature=fixture-metric"}\n'
    ordinary = "download https://storage.test/a?X-Amz-Signature=fixture-output\n"
    stderr = "pip warning, continuing\n"
    process = Mock(
        stdout=io.StringIO(ordinary + metric),
        stderr=io.StringIO(stderr),
        returncode=0,
    )
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(runner, "start_metric_emitter", Mock())
    result = runner.run_training("train.py", "v1")
    assert result.stdout == ordinary + metric
    assert result.stderr == stderr
    assert runner.parse_metric_events(result.stdout, [])[1] == {"accuracy": 0.9}
    protocol_output = capsys.readouterr().out
    assert protocol_output.startswith("METRIC_JSON:")
    assert protocol_output.count("METRIC_JSON:") == 1
    assert json.loads(protocol_output.split("METRIC_JSON:", 1)[1])["accuracy"] == 0.9
    assert "fixture-metric" not in protocol_output
    displayed = "\n".join(call.args[0] for call in writer.call_args_list)
    assert "fixture-output" not in displayed
    assert "fixture-metric" not in displayed
    assert "fixture-output" not in caplog.text
    assert all(record.levelno == logging.INFO for record in caplog.records)
    assert any("pip warning" in record.getMessage() for record in caplog.records)


def test_stderr_metric_text_does_not_become_stdout_protocol(monkeypatch, runner_workspace, log_capture, capsys):
    (runner.SOURCE_DIR / "train.py").write_text("pass", encoding="utf-8")
    marker = 'METRIC_JSON:{"accuracy":0.2}\n'
    process = Mock(stdout=io.StringIO(""), stderr=io.StringIO(marker), returncode=0)
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(return_value=process))
    monkeypatch.setattr(runner, "start_metric_emitter", Mock())
    result = runner.run_training("train.py", "v1")
    assert result.stdout == ""
    assert result.stderr == marker
    assert capsys.readouterr().out == ""


def test_pip_stderr_is_detail_not_error(monkeypatch, runner_workspace, log_capture, tmp_path):
    writer, caplog = log_capture
    writer.return_value = True
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("example-package", encoding="utf-8")
    monkeypatch.setattr(
        runner.subprocess, "run",
        Mock(return_value=subprocess.CompletedProcess([], 0, "installed\n", "pip warning\n")),
    )
    runner.install_requirements(requirements)
    assert all(record.levelno == logging.DEBUG for record in caplog.records)
    assert any("pip warning" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("failed", [False, True])
def test_execution_events_and_context_reset(monkeypatch, failed):
    runtime = Mock()
    monkeypatch.setattr(runner, "runtime_log", runtime)
    monkeypatch.setattr(runner, "configure", Mock())
    token = object()
    monkeypatch.setattr(runner, "bind_context", Mock(return_value=token))
    reset = Mock()
    monkeypatch.setattr(runner, "reset_context", reset)
    monkeypatch.setenv("TRAINING_JOB_ID", "job-test")
    run = Mock(side_effect=RuntimeError("Authorization: Bearer fixture-failure") if failed else None)
    monkeypatch.setattr(runner, "_run", run)
    if failed:
        with pytest.raises(RuntimeError):
            runner.main()
        assert runtime.event.call_args.kwargs["exc_info"] is True
    else:
        runner.main()
    assert [call.args[1] for call in runtime.event.call_args_list] == [
        "training_execution_started",
        "training_execution_failed" if failed else "training_execution_succeeded",
    ]
    assert "fixture-failure" not in str(runtime.event.call_args_list)
    assert runner.bind_context.call_args.kwargs["training_job_id"] == "job-test"
    reset.assert_called_once_with(token)
    assert runtime.event.call_args_list[0].kwargs["duration_ms"] == 0
    assert runtime.event.call_args.kwargs["duration_ms"] >= 0


@pytest.mark.parametrize("line,valid", [
    ('METRIC_JSON:{"accuracy":0.9}', True),
    ('METRIC_JSON {"cpu_percent":25}', True),
    ('METRIC_JSON:{"accuracy":0.9}\nextra line', False),
    ('METRIC_JSON:{"accuracy":0.9}\rextra line', False),
    ("METRIC_JSON:invalid", False),
    ("METRIC_JSON:[]", False),
    ("ordinary output", False),
    ("METRIC_JSON:" + " " * 16384, False),
])
def test_tenant_protocol_requires_single_line_json_object(line, valid):
    assert runner.is_metric_protocol_line(line) is valid


def test_upload_error_omits_arbitrary_response_body(monkeypatch, tmp_path):
    source = tmp_path / "model.tar.gz"
    source.write_bytes(b"model")
    monkeypatch.setattr(
        runner.requests, "put",
        Mock(return_value=Mock(status_code=500, text="private model observations")),
    )
    with pytest.raises(RuntimeError) as error:
        runner.upload_presigned_url(source, "https://storage.test/output")
    assert str(error.value) == "Presigned PUT upload failed with HTTP status 500"
