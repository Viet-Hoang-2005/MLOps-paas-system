from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from src.logging_utils import RequestLoggingMiddleware
from src.logging_utils import current_context

from src import api as index, loading


def test_worker_installs_request_logging():
    middleware = next(
        item for item in index.app.user_middleware if item.cls is RequestLoggingMiddleware
    )
    assert middleware.kwargs["routes"] is index.app.router.routes


def test_model_load_failure_and_recovery_omit_artifact_and_features(monkeypatch, tmp_path):
    summary, event = Mock(), Mock()
    model = SimpleNamespace(metadata=SimpleNamespace(signature=None))
    loader = Mock(side_effect=[RuntimeError("https://private/?token=hidden feature-payload"), model])
    monkeypatch.setattr(loading, "MODEL_CACHE", {})
    monkeypatch.setattr(loading, "load_summary", summary)
    monkeypatch.setattr(loading, "log_event", event)
    monkeypatch.setattr(loading, "download_model_artifact", lambda *_: tmp_path)
    monkeypatch.setattr(loading, "resolve_mlflow_model_dir", lambda path: path)
    monkeypatch.setattr(loading.mlflow.pyfunc, "load_model", loader)
    with pytest.raises(HTTPException) as exc:
        loading.load_model_from_uri("v", "https://private/?token=hidden")
    assert exc.value.status_code == 503
    loaded = loading.load_model_from_uri("v", "https://private/?token=hidden")
    assert loaded["model"] is model
    assert loading.load_model_from_uri("v", "https://private/?token=hidden") is loaded
    summary.failure.assert_called_once_with("load", "Model artifact load failed", error_type="RuntimeError")
    summary.recovery.assert_called_once_with("load")
    event.assert_called_once_with(loading.logger, "INFO", "model_loaded", "Model artifact loaded")
    assert "hidden" not in str(summary.mock_calls + event.mock_calls)
    assert "feature-payload" not in str(summary.mock_calls + event.mock_calls)


def test_request_context_survives_prediction_and_resets_after_request(monkeypatch):
    from fastapi.testclient import TestClient

    observed = []
    model = Mock()
    model.predict.side_effect = lambda _: observed.append(current_context()) or [1]
    monkeypatch.setattr(index, "configure", Mock())
    monkeypatch.setattr(index, "load_summary", Mock())
    monkeypatch.setenv("MODEL_VERSION_ID", "version")
    monkeypatch.setenv("MODEL_URI", "/model")
    monkeypatch.setattr(index, "load_model_from_uri", lambda *_: {"model": model})
    before = current_context()
    with TestClient(index.app) as client:
        response = client.post("/predict", json={"features": {"x": 1}}, headers={"X-Request-ID": "prediction-request"})
        assert response.status_code == 200
    assert observed[0]["request_id"] == "prediction-request"
    assert current_context() == before
