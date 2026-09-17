import json
import numpy as np
import pytest

from unittest.mock import Mock
from fastapi import HTTPException
from src import api as index


@pytest.mark.asyncio
async def test_root_health_lists_cache(monkeypatch):
    monkeypatch.setattr(index, "MODEL_CACHE", {"a": {}})
    body = await index.health_check()
    assert body["cached_models"] == ["a"]


@pytest.mark.asyncio
async def test_model_health_states(monkeypatch):
    monkeypatch.delenv("MODEL_VERSION_ID", raising=False)
    assert not (await index.model_health())["model_loaded"]
    monkeypatch.setenv("MODEL_VERSION_ID", "m")
    monkeypatch.delenv("MODEL_URI", raising=False)
    assert (await index.model_health())["status"] == "unhealthy"
    monkeypatch.setenv("MODEL_URI", "/model")
    monkeypatch.setattr(index, "load_model_from_uri", lambda *_: {"model": object()})
    assert (await index.model_health())["model_loaded"]
    monkeypatch.setattr(index, "load_model_from_uri", Mock(side_effect=RuntimeError("bad")))
    assert "bad" in (await index.model_health())["error"]


@pytest.mark.asyncio
async def test_predict_requires_model_and_uri(monkeypatch):
    monkeypatch.delenv("MODEL_VERSION_ID", raising=False)
    with pytest.raises(HTTPException) as exc:
        await index.predict(index.InferenceRequest(features={}))
    assert exc.value.status_code == 400
    monkeypatch.setenv("MODEL_VERSION_ID", "m")
    monkeypatch.delenv("MODEL_URI", raising=False)
    with pytest.raises(HTTPException) as exc:
        await index.predict(index.InferenceRequest(features={}))
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_predict_reorders_features_maps_label_and_confidence(monkeypatch):
    class Raw:
        def predict_proba(self, frame):
            return np.array([[0.2, 0.8]])

    model = Mock()
    model.predict.return_value = np.array([1])
    model._model_impl = Raw()
    monkeypatch.setenv("MODEL_VERSION_ID", "m")
    monkeypatch.setenv("MODEL_URI", "/model")
    monkeypatch.setenv("TENANT_ID", "tenant")
    monkeypatch.setattr(index, "load_model_from_uri", lambda *_: {
        "model": model,
        "expected_features": ["b", "a"],
        "label_mapping": {1: "attack"},
    })
    response = await index.predict(index.InferenceRequest(features={"a": 1, "b": 2}))
    body = json.loads(response.body)
    assert body["prediction"] == "attack"
    assert body["confidence"] == 80.0
    assert list(model.predict.call_args.args[0].columns) == ["b", "a"]


@pytest.mark.asyncio
async def test_predict_missing_expected_feature(monkeypatch):
    monkeypatch.setenv("MODEL_VERSION_ID", "m")
    monkeypatch.setenv("MODEL_URI", "/model")
    monkeypatch.setattr(index, "load_model_from_uri", lambda *_: {
        "model": Mock(), "expected_features": ["a", "b"]
    })
    with pytest.raises(HTTPException) as exc:
        await index.predict(index.InferenceRequest(features={"a": 1}))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_predict_feature_name_value_error(monkeypatch):
    model = Mock()
    model.predict.side_effect = ValueError("feature_names mismatch")
    monkeypatch.setenv("MODEL_VERSION_ID", "m")
    monkeypatch.setenv("MODEL_URI", "/model")
    monkeypatch.setattr(index, "load_model_from_uri", lambda *_: {"model": model})
    with pytest.raises(HTTPException) as exc:
        await index.predict(index.InferenceRequest(features={"a": 1}))
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "Invalid feature columns"


@pytest.mark.asyncio
async def test_predict_generic_error_is_500(monkeypatch):
    model = Mock()
    model.predict.side_effect = RuntimeError("boom")
    monkeypatch.setenv("MODEL_VERSION_ID", "m")
    monkeypatch.setenv("MODEL_URI", "/model")
    monkeypatch.setattr(index, "load_model_from_uri", lambda *_: {"model": model})
    with pytest.raises(HTTPException) as exc:
        await index.predict(index.InferenceRequest(features={"a": 1}))
    assert exc.value.status_code == 500
