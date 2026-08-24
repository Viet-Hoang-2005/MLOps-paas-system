import pandas as pd
import pytest

from unittest.mock import Mock
from src import index


def make_service(monkeypatch, model):
    monkeypatch.setattr(index, "load_runtime_model", lambda *_: model)
    return index.DeepLearningModelService()


def test_load_runtime_model_uses_resolved_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(index, "download_model_artifact", lambda *_: tmp_path)
    monkeypatch.setattr(index, "resolve_mlflow_model_dir", lambda path: path / "model")
    load = Mock(return_value="loaded")
    monkeypatch.setattr(index.mlflow.pyfunc, "load_model", load)
    assert index.load_runtime_model("m", "uri") == "loaded"
    load.assert_called_once_with(str(tmp_path / "model"))


def test_constructor_handles_load_failure(monkeypatch):
    monkeypatch.setattr(index, "load_runtime_model", Mock(side_effect=RuntimeError("bad")))
    service = index.DeepLearningModelService()
    assert service.model is None


@pytest.mark.parametrize(
    "payload,expected_rows",
    [
        ({"features": {"a": 1, "b": 2}, "model_version_id": "m"}, 1),
        ({"features": {"a": [1, 2], "b": [3, 4]}}, 2),
        ({"features": [[1, 2], [3, 4]]}, 2),
    ],
)
def test_predict_normalizes_payload(monkeypatch, payload, expected_rows):
    model = Mock()
    model.predict.side_effect = lambda frame: [1] * len(frame)
    service = make_service(monkeypatch, model)
    result = service.predict(payload)
    assert len(model.predict.call_args.args[0]) == expected_rows
    assert result["engine"] == "deep-learning-serving"


def test_predict_accepts_dataframe_and_numpy_like_result(monkeypatch):
    model = Mock()
    model.predict.return_value = pd.Series(["a", "b"])
    service = make_service(monkeypatch, model)
    result = service.predict(pd.DataFrame({"x": [1, 2]}))
    assert result["prediction"] == ["a", "b"]


def test_predict_rejects_unloaded_model(monkeypatch):
    service = make_service(monkeypatch, object())
    service.model = None
    with pytest.raises(RuntimeError, match="failed to load"):
        service.predict({"features": {"x": 1}})


def test_health_reports_model_state(monkeypatch):
    monkeypatch.setenv("MODEL_VERSION_ID", "version")
    service = make_service(monkeypatch, object())
    assert service.health()["model_loaded"] is True
    assert service.health()["model_version_id"] == "version"
