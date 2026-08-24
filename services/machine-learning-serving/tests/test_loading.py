import json
import pytest

from types import SimpleNamespace
from unittest.mock import Mock
from fastapi import HTTPException
from src import loading


def test_download_model_artifact_accepts_local_directory(tmp_path):
    assert loading.download_model_artifact("m", str(tmp_path)) == tmp_path


def test_download_model_artifact_rejects_missing_path(tmp_path):
    with pytest.raises(RuntimeError, match="Pre-built model artifact"):
        loading.download_model_artifact("m", str(tmp_path / "missing"))


def test_resolve_mlflow_model_dir_root_nested_and_missing(tmp_path):
    (tmp_path / "MLmodel").write_text("x")
    assert loading.resolve_mlflow_model_dir(tmp_path) == tmp_path
    (tmp_path / "MLmodel").unlink()
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "MLmodel").write_text("x")
    assert loading.resolve_mlflow_model_dir(tmp_path) == nested
    (nested / "MLmodel").unlink()
    with pytest.raises(FileNotFoundError):
        loading.resolve_mlflow_model_dir(tmp_path)


def test_load_model_cache_and_signature(monkeypatch, tmp_path):
    (tmp_path / "MLmodel").write_text("x")
    inputs = [SimpleNamespace(name="a"), SimpleNamespace(name="b")]
    model = SimpleNamespace(metadata=SimpleNamespace(signature=SimpleNamespace(inputs=inputs)))
    load = Mock(return_value=model)
    monkeypatch.setattr(loading.mlflow.pyfunc, "load_model", load)
    monkeypatch.setattr(loading, "download_model_artifact", lambda *_: tmp_path)
    loading.MODEL_CACHE.clear()

    first = loading.load_model_from_uri("m", "uri", "v1")
    second = loading.load_model_from_uri("m", "uri", "v1")
    loading.load_model_from_uri("m", "uri", "v2")

    assert first is second
    assert first["expected_features"] == ["a", "b"]
    assert load.call_count == 2


def test_load_label_mapping_list_becomes_dictionary(monkeypatch, tmp_path):
    (tmp_path / "MLmodel").write_text("x")
    (tmp_path / "label_classes.json").write_text(json.dumps(["safe", "attack"]))
    model = SimpleNamespace(metadata=SimpleNamespace(signature=None))
    monkeypatch.setattr(loading.mlflow.pyfunc, "load_model", lambda *_: model)
    monkeypatch.setattr(loading, "download_model_artifact", lambda *_: tmp_path)
    loading.MODEL_CACHE.clear()
    loaded = loading.load_model_from_uri("m", "uri")
    assert loaded["label_mapping"] == {0: "safe", 1: "attack"}


def test_load_model_empty_uri_and_loader_failure(monkeypatch, tmp_path):
    loading.MODEL_CACHE.clear()
    with pytest.raises(HTTPException) as exc:
        loading.load_model_from_uri("m", "")
    assert exc.value.status_code == 503
    monkeypatch.setattr(loading, "download_model_artifact", Mock(side_effect=RuntimeError("missing")))
    with pytest.raises(HTTPException, match="Unable to load"):
        loading.load_model_from_uri("m", "uri")


def test_load_model_for_record_delegates(monkeypatch):
    call = Mock(return_value={"model": "ok"})
    monkeypatch.setattr(loading, "load_model_from_uri", call)
    record = {"id": 5, "model_uri": "/m", "updated_at": "stamp"}
    assert loading.load_model_for_record(record) == {"model": "ok"}
    call.assert_called_once_with("5", "/m", "stamp")
