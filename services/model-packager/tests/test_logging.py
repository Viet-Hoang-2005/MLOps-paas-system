import logging
import sys
from unittest.mock import Mock

import pytest
from src.logging_utils import RuntimeLog

from src import tasks as cli


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    monkeypatch.setattr(cli, "runtime_log", RuntimeLog(logging.Logger("build-log-test")))
    monkeypatch.setattr(cli, "configure", Mock())


def test_setup_does_not_redirect_streams_or_attach_redis_to_container_logger(monkeypatch):
    client = Mock()
    monkeypatch.setenv("REDIS_URL", "redis://unit")
    monkeypatch.setattr(cli.redis, "from_url", Mock(return_value=client))
    stdout, stderr = sys.stdout, sys.stderr
    handlers = list(cli.logger.handlers)
    cli.setup_logger("build-test")
    cli.setup_logger("build-test")
    assert sys.stdout is stdout
    assert sys.stderr is stderr
    assert cli.logger.handlers == handlers
    cli.runtime_log.detail("packaging")
    client.rpush.assert_called_once_with("build_logs:build-test", "packaging")


def test_redis_handler_sanitizes_and_never_dumps_failed_record(monkeypatch, capsys):
    client = Mock()
    monkeypatch.setattr(cli.redis, "from_url", Mock(return_value=client))
    handler = cli.RedisLogHandler("redis://unit", "build-test")
    record = logging.LogRecord("build", logging.INFO, __file__, 1, "Authorization: Bearer fixture-bearer", (), None)
    handler.emit(record)
    assert "fixture-bearer" not in client.rpush.call_args.args[1]
    client.rpush.side_effect = RuntimeError("Authorization: Bearer fixture-redis-error")
    assert handler.write("detail") is False
    handler.emit(record)
    assert capsys.readouterr().err == ""


def test_failed_redis_setup_retains_info_fallback(monkeypatch, caplog):
    monkeypatch.setenv("REDIS_URL", "redis://unit")
    logger = logging.Logger("build-fallback-test", logging.DEBUG)
    logger.addHandler(caplog.handler)
    monkeypatch.setattr(cli, "logger", logger)
    monkeypatch.setattr(cli.redis, "from_url", Mock(side_effect=RuntimeError("offline")))
    cli.setup_logger("build-test")
    cli.runtime_log.detail("build step")
    assert caplog.records[-1].levelno == logging.INFO


@pytest.mark.parametrize("failed", [False, True])
def test_execution_events_and_failure_marker(monkeypatch, failed, capsys):
    monkeypatch.setenv("BUILD_ID", "build-test")
    monkeypatch.setenv("TASK_TYPE", "BUILD")
    monkeypatch.delenv("BUILD_ENGINE", raising=False)
    monkeypatch.setattr(cli, "setup_logger", Mock())
    runtime = Mock(wraps=cli.runtime_log)
    monkeypatch.setattr(cli, "runtime_log", runtime)
    monkeypatch.setattr(
        cli, "run_build_task",
        Mock(side_effect=RuntimeError("Authorization: Bearer fixture-failure") if failed else None),
    )
    callback = Mock()
    monkeypatch.setattr(cli, "post_webhook", callback)
    token = object()
    monkeypatch.setattr(cli, "bind_context", Mock(return_value=token))
    reset = Mock()
    monkeypatch.setattr(cli, "reset_context", reset)
    if failed:
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 1
        assert capsys.readouterr().out == "BUILD_EOF_ERROR\n"
        assert "fixture-failure" not in callback.call_args.args[1]["error_message"]
        assert runtime.event.call_args.kwargs["exc_info"] is True
    else:
        cli.main()
        callback.assert_not_called()
    assert [call.args[1] for call in runtime.event.call_args_list] == [
        "build_execution_started", "build_execution_failed" if failed else "build_execution_succeeded",
    ]
    reset.assert_called_once_with(token)
    assert runtime.event.call_args_list[0].kwargs["duration_ms"] == 0
    assert runtime.event.call_args.kwargs["duration_ms"] >= 0


@pytest.mark.parametrize("task_type,event", [
    ("BUILD", "build.preparation.completed"),
    ("TEST_ZIP", "build.preparation.completed"),
    ("NOTIFY_BUILD", "build.notification.completed"),
])
def test_kaniko_completion_names_the_local_stage(monkeypatch, task_type, event):
    monkeypatch.setenv("BUILD_ID", "build-test")
    monkeypatch.setenv("TASK_TYPE", task_type)
    monkeypatch.setenv("BUILD_ENGINE", "kaniko")
    monkeypatch.setattr(cli, "setup_logger", Mock())
    runtime = Mock()
    monkeypatch.setattr(cli, "runtime_log", runtime)
    for name in ("run_build_task", "run_test_zip_task", "run_notify_task"):
        monkeypatch.setattr(cli, name, Mock())
    cli.main()
    assert runtime.event.call_args.args[1] == event
    assert "build_execution_succeeded" not in str(runtime.event.call_args_list)


def test_notify_marker_emitted_once_without_container_duplicate(monkeypatch, tmp_path, capsys, caplog):
    logger = logging.Logger("build-protocol-test", logging.DEBUG)
    logger.addHandler(caplog.handler)
    writer = Mock(return_value=True)
    monkeypatch.setattr(cli, "runtime_log", RuntimeLog(logger, writer=writer))
    (tmp_path / "webhook_payload.json").write_text('{"build_id":"build-test"}', encoding="utf-8")
    monkeypatch.setattr(cli, "post_webhook", Mock())
    cli.run_notify_task(str(tmp_path), "https://callback.test")
    assert capsys.readouterr().out == "NOTIFY_EOF_SUCCESS\n"
    assert sum(call.args[0] == "NOTIFY_EOF_SUCCESS" for call in writer.call_args_list) == 1
    assert "NOTIFY_EOF_SUCCESS" not in caplog.text


def test_docker_details_are_sanitized_debug(monkeypatch, tmp_path, caplog):
    logger = logging.Logger("docker-log-test", logging.DEBUG)
    logger.addHandler(caplog.handler)
    writer = Mock(return_value=True)
    monkeypatch.setattr(cli, "runtime_log", RuntimeLog(logger, writer=writer))
    monkeypatch.delenv("HARBOR_REGISTRY_URL", raising=False)
    client = Mock()
    client.api.build.return_value = [{"stream": "Downloading https://storage.test/a?X-Amz-Signature=fixture-build\n"}]
    monkeypatch.setattr(cli.docker, "from_env", Mock(return_value=client))
    cli.build_custom_image(tmp_path, "build-test", "tenant-test", "")
    assert "fixture-build" not in caplog.text
    assert "fixture-build" not in str(writer.call_args_list)
    assert all(record.levelno == logging.DEBUG for record in caplog.records)


def test_webhook_error_omits_arbitrary_response_body(monkeypatch):
    monkeypatch.setattr(
        cli.requests, "post",
        Mock(return_value=Mock(status_code=500, text="private model observations")),
    )
    with pytest.raises(RuntimeError) as error:
        cli.post_webhook("https://callback.test/build", {})
    assert str(error.value) == "Build webhook failed with HTTP 500"
