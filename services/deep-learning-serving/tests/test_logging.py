from unittest.mock import Mock
import logging

from src.logging_utils import bind_context, reset_context
from src.logging_utils import RequestLoggingMiddleware

from src import service as index


def test_bentoml_uses_local_middleware_and_disables_duplicate_access_logs():
    service = index.DeepLearningModelService
    assert service.config["logging"]["access"]["enabled"] is False
    assert (RequestLoggingMiddleware, {"service": "deep-learning-serving"}) in service.middlewares


def test_worker_reconfigures_logging_and_load_failure_omits_sensitive_details(monkeypatch):
    configure, event = Mock(), Mock()
    monkeypatch.setattr(index, "configure", configure)
    monkeypatch.setattr(index, "log_event", event)
    monkeypatch.setattr(index, "load_runtime_model", Mock(side_effect=RuntimeError("https://private/?token=hidden feature-payload")))
    service = index.DeepLearningModelService()
    assert service.model is None
    configure.assert_called_once_with("deep-learning-serving")
    event.assert_called_once_with(index.logger, "ERROR", "model_load_failed", "Deep learning model load failed", error_type="RuntimeError")


def test_load_start_does_not_log_model_path(monkeypatch):
    event = Mock()
    monkeypatch.setattr(index, "log_event", event)
    monkeypatch.setattr(index, "download_model_artifact", lambda *_: "private-artifact-path")
    monkeypatch.setattr(index, "resolve_mlflow_model_dir", lambda path: path)
    monkeypatch.setattr(index.mlflow.pyfunc, "load_model", lambda _: "model")
    assert index.load_runtime_model("version", "https://private/?token=hidden") == "model"
    event.assert_called_once_with(index.logger, "INFO", "model_load_started", "Loading deep learning model")


def test_only_duplicate_bentoml_request_exceptions_are_filtered():
    duplicate = logging.LogRecord("bentoml._internal.server.http_app", logging.ERROR, "", 0, "Exception on %s [%s]", ("/predict", "POST"), None)
    operational = logging.LogRecord("bentoml._internal.server.http_app", logging.ERROR, "", 0, "Worker failed to start", (), None)
    assert index._keep_bentoml_operational_log(duplicate)
    token = bind_context(request_id="request-1")
    try:
        assert not index._keep_bentoml_operational_log(duplicate)
        assert index._keep_bentoml_operational_log(operational)
    finally:
        reset_context(token)


def test_bentoml_http_failure_is_logged_without_framework_duplicate(monkeypatch, caplog):
    from starlette.testclient import TestClient

    model = Mock()
    model.predict.side_effect = RuntimeError("feature-payload https://private/endpoint")
    monkeypatch.setattr(index, "configure", Mock())
    monkeypatch.setattr(index, "load_runtime_model", lambda *_: model)
    caplog.set_level(logging.INFO)
    with TestClient(index.DeepLearningModelService.to_asgi()) as client:
        for _ in range(2):
            response = client.post("/predict", json={"payload": {"features": {"x": "feature-payload"}}})
            assert response.status_code == 500
        assert client.post("/health", json={}).status_code == 200
    errors = [record for record in caplog.records if getattr(record, "event", "") == "http.request.failed"]
    assert len(errors) == 2
    assert not any(record.msg == "Exception on %s [%s]" for record in caplog.records)
    assert "feature-payload" not in caplog.text
