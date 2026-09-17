import json
import uuid
import httpx
import jwt
import pytest

from unittest.mock import AsyncMock, Mock
from fastapi import BackgroundTasks, HTTPException
from src import api as index, database


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self.payload = payload
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=Mock(), response=Mock())


class FakeAsyncClient:
    def __init__(self, get=None, post=None, **kwargs):
        self.get_response = get
        self.post_response = post

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, *args, **kwargs):
        if isinstance(self.get_response, Exception):
            raise self.get_response
        return self.get_response

    async def post(self, *args, **kwargs):
        if isinstance(self.post_response, Exception):
            raise self.post_response
        return self.post_response


class Metric:
    def labels(self, **kwargs):
        return self

    def inc(self):
        return None

    def observe(self, value):
        return None


@pytest.fixture(autouse=True)
def reset_globals(monkeypatch):
    index.JWKS_CACHE.clear()
    monkeypatch.setattr(index, "redis_client", None)
    monkeypatch.setattr(index, "kafka_producer", None)
    monkeypatch.setattr(index, "paas_predictions_counter", Metric())
    monkeypatch.setattr(index, "paas_latency_histogram", Metric())


@pytest.mark.asyncio
async def test_get_public_key_fetches_and_caches(monkeypatch):
    key_data = {"kid": "k", "kty": "RSA"}
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(get=FakeResponse(payload={"keys": [key_data]})))
    monkeypatch.setattr(index.RSAAlgorithm, "from_jwk", lambda value: "public")
    assert await index.get_public_key("k") == "public"
    assert await index.get_public_key("k") == "public"


@pytest.mark.asyncio
async def test_get_public_key_failure_returns_none(monkeypatch):
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(get=RuntimeError("down")))
    assert await index.get_public_key("k") is None


@pytest.mark.asyncio
async def test_access_public_and_api_key(monkeypatch):
    version = str(uuid.uuid4())
    record = {"tenant_id": "t", "access_mode": "public", "project_pk": 1}
    monkeypatch.setattr(index, "get_model_version_record", lambda *a, **k: record)
    assert (await index.verify_model_access(version, None, None))["auth_type"] == "public"
    record["access_mode"] = "private"
    monkeypatch.setattr(index, "verify_project_api_key", lambda *_: {"tenant_id": "t"})
    assert (await index.verify_model_access(version, "key", None))["auth_type"] == "api_key"


@pytest.mark.asyncio
async def test_access_api_key_invalid_and_cross_tenant(monkeypatch):
    version = str(uuid.uuid4())
    record = {"tenant_id": "t", "access_mode": "private", "project_pk": 1}
    monkeypatch.setattr(index, "get_model_version_record", lambda *a, **k: record)
    monkeypatch.setattr(index, "verify_project_api_key", lambda *_: None)
    with pytest.raises(HTTPException) as exc:
        await index.verify_model_access(version, "bad", None)
    assert exc.value.status_code == 401
    monkeypatch.setattr(index, "verify_project_api_key", lambda *_: {"tenant_id": "other"})
    with pytest.raises(HTTPException) as exc:
        await index.verify_model_access(version, "key", None)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_access_jwt_success_missing_and_tenant_mismatch(monkeypatch):
    version = str(uuid.uuid4())
    record = {"tenant_id": "t", "access_mode": "private", "project_pk": 1}
    monkeypatch.setattr(index, "get_model_version_record", lambda *a, **k: record)
    with pytest.raises(HTTPException) as exc:
        await index.verify_model_access(version, None, None)
    assert exc.value.status_code == 401
    monkeypatch.setattr(index.jwt, "get_unverified_header", lambda token: {"kid": "k"})
    monkeypatch.setattr(index, "get_public_key", AsyncMock(return_value="public"))
    monkeypatch.setattr(index.jwt, "decode", lambda *a, **k: {"tenant_id": "t"})
    assert (await index.verify_model_access(version, None, "Bearer token"))["auth_type"] == "jwt"
    monkeypatch.setattr(index.jwt, "decode", lambda *a, **k: {"tenant_id": "other"})
    with pytest.raises(HTTPException) as exc:
        await index.verify_model_access(version, None, "Bearer token")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_access_jwt_missing_kid_expired_and_invalid(monkeypatch):
    version = str(uuid.uuid4())
    record = {"tenant_id": "t", "access_mode": "private", "project_pk": 1}
    monkeypatch.setattr(index, "get_model_version_record", lambda *a, **k: record)
    monkeypatch.setattr(index.jwt, "get_unverified_header", lambda token: {})
    with pytest.raises(HTTPException) as exc:
        await index.verify_model_access(version, None, "Bearer token")
    assert exc.value.status_code == 401
    monkeypatch.setattr(index.jwt, "get_unverified_header", lambda token: {"kid": "k"})
    monkeypatch.setattr(index, "get_public_key", AsyncMock(return_value="public"))
    monkeypatch.setattr(index.jwt, "decode", Mock(side_effect=jwt.ExpiredSignatureError()))
    with pytest.raises(HTTPException) as exc:
        await index.verify_model_access(version, None, "Bearer token")
    assert exc.value.status_code == 401
    monkeypatch.setattr(index.jwt, "decode", Mock(side_effect=jwt.InvalidTokenError("bad")))
    with pytest.raises(HTTPException) as exc:
        await index.verify_model_access(version, None, "Bearer token")
    assert exc.value.status_code == 401


def test_resolve_worker_url_local_and_kubernetes(monkeypatch):
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    assert index.resolve_worker_url({"flavor": "xgboost"}, "/predict") == "http://machine-learning-serving:5001/predict"
    assert index.resolve_worker_url({"flavor": "pytorch"}, "/health") == "http://deep-learning-serving:5002/health"
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "yes")
    assert index.resolve_worker_url({"flavor": "tensorflow", "endpoint_container_name": "worker"}, "/predict") == "http://worker-svc.mlops-model-runtimes.svc.cluster.local:5002/predict"
    with pytest.raises(HTTPException) as exc:
        index.resolve_worker_url({"flavor": "sklearn"}, "/predict")
    assert exc.value.status_code == 503


def test_serving_engine_is_derived_from_version_flavor():
    assert index.serving_engine_for_flavor("pytorch") == "dl"
    assert index.serving_engine_for_flavor("TensorFlow") == "dl"
    assert index.serving_engine_for_flavor("xgboost") == "ml"
    assert index.serving_engine_for_flavor(None) == "ml"


def test_send_to_redpanda_payload_and_failure(monkeypatch):
    producer = Mock()
    monkeypatch.setattr(index, "kafka_producer", producer)
    index.send_to_redpanda(
        "t", "p", "v", {"x": 1}, "safe",
        prediction_id="pred-123", confidence=91.0, latency_ms=12.5, status_code=200, request_id="req-1"
    )
    value = json.loads(producer.produce.call_args.kwargs["value"])
    assert value["tenant_id"] == "t" and value["prediction"] == "safe"
    assert value["project_id"] == "p" and value["model_version_id"] == "v"
    assert value["id"] == "pred-123"
    assert value["prediction_id"] == "pred-123"
    assert value["confidence"] == 91.0
    assert value["latency_ms"] == 12.5
    assert value["status_code"] == 200
    assert value["request_id"] == "req-1"
    producer.produce.side_effect = RuntimeError("down")
    index.send_to_redpanda("t", "p", "v", {}, None)


@pytest.mark.asyncio
async def test_health_proxy_success_and_failure(monkeypatch):
    token = {"model_record": {"flavor": "sklearn", "endpoint_container_name": "worker"}}
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(get=FakeResponse(payload={"status": "healthy"})))
    assert (await index.model_health("v", token))["status"] == "healthy"
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(get=FakeResponse(500, text="bad")))
    assert (await index.model_health("v", token)).status_code == 500
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(get=RuntimeError("down")))
    assert (await index.model_health("v", token)).status_code == 503


@pytest.mark.asyncio
async def test_predict_proxy_success_and_background_event(monkeypatch):
    record = {
        "id": "version",
        "project_id": "project",
        "tenant_id": "t",
        "flavor": "xgboost",
        "endpoint_container_name": "worker",
    }
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(post=FakeResponse(payload={
        "prediction": "attack", "confidence": 91.0, "engine": "machine-learning-serving"
    })))
    tasks = BackgroundTasks()
    response = await index.predict("v", Mock(), index.InferenceRequest(features={"x": 1}), tasks, {"model_record": record})
    body = json.loads(response.body)
    assert body["prediction"] == "attack"
    assert "prediction_id" in body
    uuid.UUID(body["prediction_id"])
    assert len(tasks.tasks) == 1


@pytest.mark.asyncio
async def test_predict_upstream_and_network_errors(monkeypatch):
    record = {
        "id": "version",
        "project_id": "project",
        "tenant_id": "t",
        "flavor": "xgboost",
        "endpoint_container_name": "worker",
    }
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(post=FakeResponse(422, {"detail": "bad"})))
    response = await index.predict("v", Mock(), index.InferenceRequest(features={}), BackgroundTasks(), {"model_record": record})
    assert response.status_code == 422
    request_error = httpx.RequestError("down", request=Mock())
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(post=request_error))
    with pytest.raises(HTTPException) as exc:
        await index.predict("v", Mock(), index.InferenceRequest(features={}), BackgroundTasks(), {"model_record": record})
    assert exc.value.status_code == 503


def test_runtime_factories_fail_closed(monkeypatch):
    monkeypatch.setattr(index.redis, "from_url", Mock(side_effect=RuntimeError("no")))
    monkeypatch.setattr(index, "Producer", Mock(side_effect=RuntimeError("no")))
    assert index.create_redis_client() is None
    assert index.create_kafka_producer() is None


def test_invalidate_model_version_cache():
    fake_redis = Mock()
    fake_redis.delete.return_value = 1
    assert database.invalidate_model_version_cache("v123", fake_redis) is True
    fake_redis.delete.assert_called_once_with("model-version:v123")
    assert database.invalidate_model_version_cache("", fake_redis) is False
    assert database.invalidate_model_version_cache("v123", None) is False


@pytest.mark.asyncio
async def test_predict_network_error_evicts_cache_and_returns_409_if_stopped(monkeypatch):
    record = {
        "id": "v-stopped",
        "project_id": "proj",
        "tenant_id": "t",
        "flavor": "sklearn",
        "endpoint_container_name": "worker-stopped",
        "deployment_status": "healthy",
    }
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    fake_redis = Mock()
    monkeypatch.setattr(index, "redis_client", fake_redis)

    request_error = httpx.RequestError("Connection refused", request=Mock())
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda **kw: FakeAsyncClient(post=request_error))

    stopped_db_record = {
        "id": "v-stopped",
        "project_id": "proj",
        "tenant_id": "t",
        "flavor": "sklearn",
        "endpoint_container_name": None,
        "deployment_status": "stopped",
    }
    monkeypatch.setattr(index, "_fetch_model_version_from_db", lambda vid: stopped_db_record)

    with pytest.raises(HTTPException) as exc:
        await index.predict(
            "v-stopped",
            Mock(),
            index.InferenceRequest(features={}),
            BackgroundTasks(),
            {"model_record": record},
        )

    fake_redis.delete.assert_called_with("model-version:v-stopped")
    assert exc.value.status_code == 409
    assert "stopped" in exc.value.detail.lower()


def test_resolve_worker_url_rejects_stopped_deployment(monkeypatch):
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    stopped_record = {
        "flavor": "sklearn",
        "endpoint_container_name": None,
        "deployment_status": "stopped",
    }
    with pytest.raises(HTTPException) as exc:
        index.resolve_worker_url(stopped_record, "/predict")
    assert exc.value.status_code == 409
