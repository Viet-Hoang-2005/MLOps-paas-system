import json
import logging
import zipfile
import pandas as pd
import pytest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from src import main


class Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *args):
        return False


def test_validate_runtime_config(monkeypatch):
    monkeypatch.setattr(main, "TENANT_ID", "t")
    monkeypatch.setattr(main, "PROJECT_ID", "p")
    monkeypatch.setattr(main, "MODEL_VERSION_ID", "v")
    monkeypatch.setattr(main, "DRIFT_THRESHOLD", 0.5)
    main.validate_runtime_config()
    monkeypatch.setattr(main, "DRIFT_THRESHOLD", 1.5)
    with pytest.raises(ValueError, match="DRIFT_THRESHOLD"):
        main.validate_runtime_config()
    monkeypatch.setattr(main, "DRIFT_THRESHOLD", 0.5)
    monkeypatch.setattr(main, "MODEL_VERSION_ID", None)
    with pytest.raises(ValueError, match="MODEL_VERSION_ID"):
        main.validate_runtime_config()


def test_redis_log_handler_writes_run_scoped_stream(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.calls = []

        def delete(self, key):
            self.calls.append(("delete", key))

        def rpush(self, key, value):
            self.calls.append(("rpush", key, value))

        def expire(self, key, ttl):
            self.calls.append(("expire", key, ttl))

    fake = FakeRedis()
    monkeypatch.setattr(main.redis, "from_url", lambda _url: fake)
    handler = main.RedisLogHandler("redis://unit", "run-uuid")
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(logging.LogRecord("drift", logging.INFO, __file__, 1, "running report", (), None))

    assert fake.calls == [
        ("delete", "drift_logs:run-uuid"),
        ("rpush", "drift_logs:run-uuid", "running report"),
        ("expire", "drift_logs:run-uuid", 3600),
    ]


def test_load_reference_local_csv(monkeypatch, tmp_path):
    path = tmp_path / "reference.csv"
    pd.DataFrame({"x": [1, 2]}).to_csv(path, index=False)
    monkeypatch.setattr(main, "REFERENCE_DATA_URL", str(path))
    assert main.load_reference_data().to_dict("list") == {"x": [1, 2]}


def test_load_reference_http_success_and_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "MODEL_VERSION_ID", "unit")
    monkeypatch.setattr(main, "TEMP_ROOT", tmp_path)
    monkeypatch.setattr(main, "REFERENCE_DATA_URL", "https://storage/reference.csv")
    monkeypatch.setattr(main.requests, "get", Mock(return_value=SimpleNamespace(status_code=200, content=b"x\n1\n", text="")))
    assert main.load_reference_data()["x"].tolist() == [1]
    monkeypatch.setattr(main.requests, "get", Mock(return_value=SimpleNamespace(status_code=404, content=b"", text="missing")))
    with pytest.raises(FileNotFoundError):
        main.load_reference_data()


def test_load_reference_requires_url(monkeypatch):
    monkeypatch.setattr(main, "REFERENCE_DATA_URL", "")
    with pytest.raises(ValueError):
        main.load_reference_data()


def test_load_production_data_flattens_json(monkeypatch):
    monkeypatch.setattr(main, "MODEL_VERSION_ID", "m")
    monkeypatch.setattr(main, "MIN_SAMPLES", 2)
    raw = pd.DataFrame({"features": [json.dumps({"a": 1}), json.dumps({"a": 2})], "prediction": ["x", "y"]})
    monkeypatch.setattr(main, "create_engine", lambda *_: SimpleNamespace(connect=lambda: Context(object())))
    monkeypatch.setattr(main.pd, "read_sql", lambda *a, **k: raw)
    result = main.load_production_data()
    assert result.to_dict("list") == {"a": [1, 2], "prediction": ["x", "y"]}


def test_load_production_data_insufficient_returns_empty(monkeypatch):
    monkeypatch.setattr(main, "MIN_SAMPLES", 3)
    monkeypatch.setattr(main, "create_engine", lambda *_: SimpleNamespace(connect=lambda: Context(object())))
    monkeypatch.setattr(main.pd, "read_sql", lambda *a, **k: pd.DataFrame({"features": [{"a": 1}]}))
    assert main.load_production_data().empty


def test_resolve_model_directory(monkeypatch, tmp_path):
    nested = tmp_path / "model"
    nested.mkdir()
    (nested / "MLmodel").write_text("x")
    assert main.resolve_model_dir(str(tmp_path)) == str(nested)
    assert main.resolve_model_dir("models:/name/1") is None


def test_safe_extract_zip_rejects_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", "bad")
    with pytest.raises(ValueError, match="unsafe"):
        main.safe_extract_zip(archive, tmp_path / "out")

    sibling_archive = tmp_path / "sibling.zip"
    with zipfile.ZipFile(sibling_archive, "w") as handle:
        handle.writestr("../outside/file.txt", "bad")
    with pytest.raises(ValueError, match="unsafe"):
        main.safe_extract_zip(sibling_archive, tmp_path / "out")


def test_safe_extract_zip_extracts_valid_archive(tmp_path):
    archive = tmp_path / "ok.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("model/MLmodel", "ok")
    destination = tmp_path / "out"
    main.safe_extract_zip(archive, destination)
    assert (destination / "model" / "MLmodel").read_text() == "ok"


def test_column_mapping_fallback_and_prediction_mapping(monkeypatch):
    monkeypatch.setattr(main, "MODEL_URI", "models:/none/Production")
    reference = pd.DataFrame({"a": [1.0], "label": ["safe"]})
    production = pd.DataFrame({"a": [2.0], "prediction": ["safe"]})
    mapping = main.get_column_mapping(reference, production)
    assert mapping.numerical_features == ["a"]
    assert mapping.prediction == "prediction"
    assert reference["prediction"].tolist() == ["safe"]


def test_column_mapping_uses_mlflow_signature(monkeypatch):
    signature = SimpleNamespace(inputs=[SimpleNamespace(name="num", type="double"), SimpleNamespace(name="cat", type="string")])
    monkeypatch.setattr(main, "resolve_model_dir", lambda _: "/model")
    monkeypatch.setattr(main.mlflow.models, "get_model_info", lambda _: SimpleNamespace(signature=signature))
    mapping = main.get_column_mapping(pd.DataFrame({"num": [1], "cat": ["a"]}), pd.DataFrame({"num": [2], "cat": ["b"]}))
    assert mapping.numerical_features == ["num"]
    assert mapping.categorical_features == ["cat"]


def test_filter_column_mapping():
    mapping = main.ColumnMapping()
    mapping.numerical_features = ["a", "missing"]
    mapping.categorical_features = ["b"]
    mapping.target = "target"
    mapping.prediction = "prediction"
    filtered = main.filter_column_mapping(mapping, ["a", "prediction"])
    assert filtered.numerical_features == ["a"]
    assert filtered.categorical_features == []
    assert filtered.prediction == "prediction"


def test_run_drift_analysis_summary(monkeypatch):
    result = {"metrics": [
        {"result": {"dataset_drift": True, "share_of_drifted_columns": 0.75, "number_of_drifted_columns": 1}},
        {"result": {"drift_by_columns": {"a": {"drift_detected": True}, "b": {"drift_detected": False}}}},
    ]}

    class FakeReport:
        def __init__(self, metrics):
            self.metrics = metrics

        def run(self, **kwargs):
            self.kwargs = kwargs

        def as_dict(self):
            return result

    monkeypatch.setattr(main, "Report", FakeReport)
    monkeypatch.setattr(main, "save_drift_report", lambda *a: {"summary_json_s3_uri": "s3://report"})
    monkeypatch.setattr(main, "TENANT_ID", "t")
    monkeypatch.setattr(main, "PROJECT_ID", "p")
    monkeypatch.setattr(main, "MODEL_VERSION_ID", "v")
    monkeypatch.setattr(main, "DRIFT_THRESHOLD", 0.6)
    frame = pd.DataFrame({"a": [1.0], "b": [2.0]})
    summary = main.run_drift_analysis(frame, frame.copy(), main.ColumnMapping())
    assert summary["dataset_drift"] is True
    assert summary["drifted_feature_names"] == ["a"]


def test_run_drift_analysis_requires_common_columns():
    with pytest.raises(ValueError, match="No common columns"):
        main.run_drift_analysis(pd.DataFrame({"a": [1]}), pd.DataFrame({"b": [1]}), main.ColumnMapping())


def test_save_report_without_upload(monkeypatch, tmp_path):
    report = Mock()
    report.save_html.side_effect = lambda path: Path(path).write_text("html")
    monkeypatch.setattr(main, "TENANT_ID", "t")
    monkeypatch.setattr(main, "MODEL_NAME", "m")
    monkeypatch.setattr(main, "TEMP_ROOT", tmp_path)
    monkeypatch.setattr(main, "HTML_UPLOAD_URL", "")
    artifacts = main.save_drift_report(report, {"metrics": []}, {"dataset_drift": False})
    assert Path(artifacts["local_summary_json_path"]).exists()


def test_save_report_uploads_artifacts(monkeypatch, tmp_path):
    report = Mock()
    report.save_html.side_effect = lambda path: Path(path).write_text("html")
    monkeypatch.setattr(main, "TENANT_ID", "t")
    monkeypatch.setattr(main, "MODEL_NAME", "m")
    monkeypatch.setattr(main, "TEMP_ROOT", tmp_path)
    monkeypatch.setattr(main, "HTML_UPLOAD_URL", "http://html")
    monkeypatch.setattr(main, "REPORT_JSON_UPLOAD_URL", "http://report")
    monkeypatch.setattr(main, "SUMMARY_JSON_UPLOAD_URL", "http://summary")
    response = Mock()
    response.raise_for_status.return_value = None
    put = Mock(return_value=response)
    monkeypatch.setattr(main.requests, "put", put)
    artifacts = main.save_drift_report(report, {}, {"dataset_drift": False})
    assert put.call_count == 4
    assert "html_s3_uri" in artifacts


def test_trigger_webhook_payload(monkeypatch):
    monkeypatch.setattr(main, "CONTROL_PLANE_WEBHOOK_URL", "http://control")
    monkeypatch.setattr(main, "CONTROL_PLANE_WEBHOOK_SECRET", "secret")
    monkeypatch.setattr(main, "TENANT_ID", "t")
    monkeypatch.setattr(main, "PROJECT_ID", "p")
    monkeypatch.setattr(main, "MODEL_VERSION_ID", "v")
    response = SimpleNamespace(status_code=200, text="")
    session = Mock()
    session.post.return_value = response
    monkeypatch.setattr(main.requests, "Session", lambda: session)
    main.trigger_django_webhook({"dataset_drift": True})
    assert session.post.call_args.kwargs["headers"]["Authorization"] == "Bearer secret"
    assert session.post.call_args.kwargs["json"]["project_id"] == "p"
    assert session.post.call_args.kwargs["json"]["model_version_id"] == "v"


def test_main_success_and_failure_paths(monkeypatch):
    monkeypatch.setattr(main, "validate_runtime_config", lambda: None)
    monkeypatch.setattr(main, "MIN_SAMPLES", 1)
    frame = pd.DataFrame({"a": [1]})
    monkeypatch.setattr(main, "load_production_data", lambda: frame)
    monkeypatch.setattr(main, "load_reference_data", lambda: frame)
    monkeypatch.setattr(main, "get_column_mapping", lambda *a: main.ColumnMapping())
    monkeypatch.setattr(main, "run_drift_analysis", lambda *a: {"dataset_drift": False})
    webhook = Mock()
    monkeypatch.setattr(main, "trigger_django_webhook", webhook)
    assert main.main() == 0
    webhook.assert_called_once()
    monkeypatch.setattr(main, "load_production_data", Mock(side_effect=RuntimeError("db")))
    assert main.main() == 1


def test_main_invalid_config_and_insufficient_samples(monkeypatch):
    monkeypatch.setattr(main, "validate_runtime_config", Mock(side_effect=ValueError("bad")))
    assert main.main() == 1
    monkeypatch.setattr(main, "validate_runtime_config", lambda: None)
    monkeypatch.setattr(main, "MIN_SAMPLES", 2)
    monkeypatch.setattr(main, "load_production_data", lambda: pd.DataFrame({"a": [1]}))
    assert main.main() == 0
