import logging
import sys
from unittest.mock import Mock

import pandas as pd
import pytest
from src.logging_utils import RuntimeLog

from src import application as main


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    monkeypatch.setattr(main, "runtime_log", RuntimeLog(logging.Logger("drift-log-test")))
    monkeypatch.setattr(main, "configure", Mock())


@pytest.mark.parametrize("redis_url", ["", "redis://unit"])
def test_setup_preserves_streams_and_container_handlers(monkeypatch, redis_url):
    monkeypatch.setattr(main, "REDIS_URL", redis_url)
    client = Mock()
    monkeypatch.setattr(main.redis, "from_url", Mock(return_value=client))
    stdout, stderr = sys.stdout, sys.stderr
    handlers = list(main.logger.handlers)
    assert main.setup_logger("run-test") is main.logger
    main.setup_logger("run-test")
    assert sys.stdout is stdout
    assert sys.stderr is stderr
    assert main.logger.handlers == handlers
    main.runtime_log.detail("report step")
    if redis_url:
        client.rpush.assert_called_once_with("drift_logs:run-test", "report step")
    else:
        client.rpush.assert_not_called()


def test_redis_handler_sanitizes_and_reports_delivery_failure(monkeypatch, capsys):
    client = Mock()
    monkeypatch.setattr(main.redis, "from_url", Mock(return_value=client))
    handler = main.RedisLogHandler("redis://unit", "run-test")
    record = logging.LogRecord("drift", logging.INFO, __file__, 1, "Authorization: Bearer fixture-bearer", (), None)
    handler.emit(record)
    assert "fixture-bearer" not in client.rpush.call_args.args[1]
    client.expire.side_effect = RuntimeError("offline")
    assert handler.write("report step") is False
    handler.emit(record)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("result", [0, 1])
def test_execution_events_reflect_local_return_value_and_reset_context(monkeypatch, result):
    runtime = Mock()
    monkeypatch.setattr(main, "runtime_log", runtime)
    monkeypatch.setattr(main, "setup_logger", Mock())
    monkeypatch.setattr(main, "_run", Mock(return_value=result))
    token = object()
    monkeypatch.setattr(main, "bind_context", Mock(return_value=token))
    reset = Mock()
    monkeypatch.setattr(main, "reset_context", reset)
    assert main.main() == result
    assert [call.args[1] for call in runtime.event.call_args_list] == [
        "drift_execution_started", "drift.execution.exited",
    ]
    assert runtime.event.call_args.kwargs["exit_code"] == result
    assert runtime.event.call_args_list[0].kwargs["duration_ms"] == 0
    assert runtime.event.call_args.kwargs["duration_ms"] >= 0
    reset.assert_called_once_with(token)


def test_uncaught_execution_error_is_sanitized_and_context_reset(monkeypatch):
    runtime = Mock()
    monkeypatch.setattr(main, "runtime_log", runtime)
    monkeypatch.setattr(main, "setup_logger", Mock())
    monkeypatch.setattr(main, "_run", Mock(side_effect=RuntimeError("Authorization: Bearer fixture-failure")))
    monkeypatch.setattr(main, "bind_context", Mock(return_value=object()))
    reset = Mock()
    monkeypatch.setattr(main, "reset_context", reset)
    with pytest.raises(RuntimeError):
        main.main()
    assert runtime.event.call_args.args[1] == "drift_execution_failed"
    assert runtime.event.call_args.kwargs["exc_info"] is True
    assert "fixture-failure" not in str(runtime.event.call_args)
    reset.assert_called_once()


def test_summary_is_one_compact_event_and_report_payload_unchanged(monkeypatch, caplog):
    logger = logging.Logger("drift-summary-test", logging.DEBUG)
    logger.addHandler(caplog.handler)
    writer = Mock(return_value=True)
    monkeypatch.setattr(main, "runtime_log", RuntimeLog(logger, writer=writer))
    report = Mock()
    report.as_dict.return_value = {"metrics": []}
    monkeypatch.setattr(main, "Report", Mock(return_value=report))
    save = Mock(return_value={})
    monkeypatch.setattr(main, "save_drift_report", save)
    reference = pd.DataFrame({"x": [1, 2], "missing": [3, 4]})
    production = pd.DataFrame({"x": [2, 3]})
    summary = main.run_drift_analysis(reference, production, main.ColumnMapping())
    events = [record for record in caplog.records if record.event == "drift_analysis_summary"]
    assert len(events) == 1
    assert events[0].drift_detected is True
    assert events[0].features_count == 2
    assert events[0].count == 1
    assert summary["missing_features"] == ["missing"]
    assert save.call_args.args[2] is summary
    assert "SUMMARY OF DATA DRIFT" not in caplog.text


def test_failed_callback_omits_response_body_without_changing_payload(monkeypatch):
    runtime = Mock()
    monkeypatch.setattr(main, "runtime_log", runtime)
    session = Mock()
    session.post.return_value = Mock(status_code=500, text="private callback response body")
    monkeypatch.setattr(main.requests, "Session", Mock(return_value=session))
    summary = {"dataset_drift": True}
    main.trigger_django_webhook(summary)
    assert session.post.call_args.kwargs["json"]["drift_summary"] is summary
    assert runtime.event.call_args.args[1] == "drift_callback_failed"
    assert runtime.event.call_args.kwargs == {"status_code": 500}
    assert "private callback response body" not in str(runtime.event.call_args)


def test_failed_upload_counts_delivery_without_claiming_success(monkeypatch, tmp_path):
    runtime = Mock()
    monkeypatch.setattr(main, "runtime_log", runtime)
    monkeypatch.setattr(main, "TEMP_ROOT", tmp_path)
    monkeypatch.setattr(main, "HTML_UPLOAD_URL", "https://storage.test/html")
    monkeypatch.setattr(main, "REPORT_JSON_UPLOAD_URL", "https://storage.test/report")
    monkeypatch.setattr(main, "SUMMARY_JSON_UPLOAD_URL", "https://storage.test/summary")
    report = Mock()
    report.save_html.side_effect = lambda path: main.Path(path).write_text("report", encoding="utf-8")
    monkeypatch.setattr(main.requests, "put", Mock(side_effect=RuntimeError("offline")))
    artifacts = main.save_drift_report(report, {}, {})
    assert "local_html_path" in artifacts
    runtime.detail.assert_called_once_with("Drift report upload attempts finished: 0/3 files uploaded.")
    assert len(runtime.event.call_args_list) == 4


def test_skipped_execution_does_not_claim_success(monkeypatch):
    runtime = Mock()
    monkeypatch.setattr(main, "runtime_log", runtime)
    monkeypatch.setattr(main, "setup_logger", Mock())
    monkeypatch.setattr(main, "validate_runtime_config", Mock())
    monkeypatch.setattr(main, "MIN_SAMPLES", 2)
    monkeypatch.setattr(main, "load_production_data", Mock(return_value=pd.DataFrame({"x": [1]})))
    assert main.main() == 0
    events = [call.args[1] for call in runtime.event.call_args_list]
    assert events == ["drift_execution_started", "drift_analysis_skipped", "drift.execution.exited"]


def test_handled_execution_failure_has_one_error_diagnosis(monkeypatch):
    runtime = Mock()
    monkeypatch.setattr(main, "runtime_log", runtime)
    monkeypatch.setattr(main, "setup_logger", Mock())
    monkeypatch.setattr(main, "validate_runtime_config", Mock())
    monkeypatch.setattr(main, "load_production_data", Mock(side_effect=RuntimeError("offline")))
    assert main.main() == 1
    errors = [call for call in runtime.event.call_args_list if call.args[0] == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].args[1] == "drift_production_data_failed"
    assert errors[0].kwargs["exc_info"] is True
    assert runtime.event.call_args.args[1] == "drift.execution.exited"
    assert runtime.event.call_args.kwargs["exit_code"] == 1


def test_reference_download_error_omits_arbitrary_response_body(monkeypatch):
    monkeypatch.setattr(main, "REFERENCE_DATA_URL", "https://storage.test/reference.csv")
    monkeypatch.setattr(
        main.requests, "get",
        Mock(return_value=Mock(status_code=404, text="private model observations")),
    )
    with pytest.raises(FileNotFoundError) as error:
        main.load_reference_data()
    assert str(error.value) == "Storage returned HTTP 404"
