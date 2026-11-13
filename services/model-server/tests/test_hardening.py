"""Request size limit, shared worker client, event-loop safety and error disclosure."""

import threading
from unittest.mock import Mock

import httpx
import jwt
import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from src import api as index
from src import auth as auth_service

SECRET = "10.0.13.7:5001 /srv/models/tenant-secret/model.pkl"
VERSION = "00000000-0000-0000-0000-000000000001"


class Metric:
    def labels(self, **kwargs):
        return self

    def inc(self):
        return None

    def observe(self, value):
        return None


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(index, "redis_client", None)
    monkeypatch.setattr(index, "kafka_producer", None)
    monkeypatch.setattr(index, "paas_predictions_counter", Metric())
    monkeypatch.setattr(index, "paas_latency_histogram", Metric())
    monkeypatch.setattr(index, "worker_client", None)


class Worker:
    def __init__(self, post=None, get=None):
        self._post, self._get = post, get
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if isinstance(self._post, Exception):
            raise self._post
        return self._post

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if isinstance(self._get, Exception):
            raise self._get
        return self._get


def response(status=200, payload=None, text=""):
    result = Mock(status_code=status, text=text)
    result.json.return_value = payload
    return result


RECORD = {
    "id": "version",
    "project_id": "project",
    "tenant_id": "tenant",
    "flavor": "sklearn",
    "endpoint_container_name": "worker",
    "deployment_status": "succeeded",
}


async def call_predict():
    request = Request({"type": "http", "headers": []})
    return await index.predict(
        "v", request, index.InferenceRequest(features={}), BackgroundTasks(), {"model_record": dict(RECORD)}
    )


# ---- request size ---------------------------------------------------------------------------


def make_probe(max_bytes):
    inner = FastAPI()
    seen = []

    @inner.post("/echo")
    async def echo(request: Request):
        seen.append(len(await request.body()))
        return {"size": seen[-1]}

    inner.add_middleware(index.BodySizeLimitMiddleware, max_bytes=max_bytes)
    return inner, seen


@pytest.mark.asyncio
async def test_declared_oversize_body_is_refused_before_the_handler_runs():
    app, seen = make_probe(100)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.post("/echo", content=b"x" * 101)).status_code == 413
        assert (await client.post("/echo", content=b"x" * 100)).json() == {"size": 100}
    assert seen == [100]


@pytest.mark.asyncio
async def test_undeclared_streamed_body_is_cut_off_at_the_limit():
    app, seen = make_probe(100)

    async def chunks():
        for _ in range(10):
            yield b"x" * 30  # no Content-Length: the size is only known while streaming

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        reply = await client.post("/echo", content=chunks())
    assert reply.status_code == 413
    assert seen == []


@pytest.mark.asyncio
async def test_gateway_enforces_a_default_limit_and_keeps_cors_headers():
    assert index.MAX_REQUEST_BODY_BYTES == 1024 * 1024
    big = b"{" + b" " * (index.MAX_REQUEST_BODY_BYTES + 1) + b"}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=index.app), base_url="http://gw") as client:
        reply = await client.post(
            f"/models/{VERSION}/predict",
            content=big,
            headers={"Origin": "http://localhost:5173", "Content-Type": "application/json"},
        )
    assert reply.status_code == 413
    assert reply.headers["access-control-allow-origin"] == "*"


# ---- shared worker client -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_client_is_created_once_and_reused(monkeypatch):
    created = []

    class Client(Worker):
        def __init__(self, **kwargs):
            super().__init__(post=response(payload={"prediction": 1}))
            created.append(kwargs)

    monkeypatch.setattr(index.httpx, "AsyncClient", Client)
    monkeypatch.setattr(index.httpx, "Limits", httpx.Limits)
    for _ in range(3):
        assert (await call_predict()).status_code == 200
    assert len(created) == 1
    assert created[0]["limits"].max_connections == index.WORKER_MAX_CONNECTIONS
    # Each call still carries its own timeout, because the pool is shared.
    assert all(call[2]["timeout"] == index.PREDICT_TIMEOUT_SECONDS for call in index.worker_client.calls)


@pytest.mark.asyncio
async def test_lifespan_opens_and_closes_the_shared_client(monkeypatch):
    monkeypatch.setattr(index, "create_redis_client", lambda: None)
    monkeypatch.setattr(index, "create_kafka_producer", lambda: None)
    app = FastAPI()
    async with index.lifespan(app):
        client = index.worker_client
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed
    assert client.is_closed
    assert index.worker_client is None


# ---- blocking I/O stays off the event loop --------------------------------------------------


@pytest.mark.asyncio
async def test_registry_and_api_key_lookups_run_in_a_worker_thread():
    main = threading.get_ident()
    threads = {}

    def lookup(version_id, redis_client=None):
        threads["registry"] = threading.get_ident()
        return {"tenant_id": "t", "access_mode": "private", "project_pk": 1}

    def verify_key(raw, project_pk):
        threads["key"] = threading.get_ident()
        return {"tenant_id": "t"}

    result = await auth_service.authorize_model_access(
        VERSION,
        "key",
        None,
        redis_client=None,
        get_model_version_record=lookup,
        verify_project_api_key=verify_key,
        get_public_key=None,
        jwt_module=jwt,
    )
    assert result["auth_type"] == "api_key"
    assert threads["registry"] != main and threads["key"] != main


@pytest.mark.asyncio
async def test_cache_invalidation_after_worker_failure_runs_in_a_worker_thread(monkeypatch):
    main = threading.get_ident()
    threads = []
    monkeypatch.setattr(index, "invalidate_model_version_cache", lambda *a, **k: threads.append(threading.get_ident()))
    monkeypatch.setattr(index, "_fetch_model_version_from_db", lambda *a, **k: threads.append(threading.get_ident()))
    monkeypatch.setattr(index, "worker_client", Worker(post=httpx.ConnectError("down", request=Mock())))
    with pytest.raises(HTTPException) as exc:
        await call_predict()
    assert exc.value.status_code == 503
    assert len(threads) == 2 and main not in threads


# ---- nothing internal reaches the caller ----------------------------------------------------


@pytest.mark.asyncio
async def test_unexpected_failure_returns_a_generic_500_without_the_exception_text(monkeypatch):
    monkeypatch.setattr(index, "worker_client", Worker(post=RuntimeError(SECRET)))
    with pytest.raises(HTTPException) as exc:
        await call_predict()
    assert exc.value.status_code == 500
    assert "10.0.13.7" not in exc.value.detail and "tenant-secret" not in exc.value.detail


@pytest.mark.asyncio
async def test_unreachable_worker_503_does_not_expose_the_address(monkeypatch):
    monkeypatch.setattr(index, "_fetch_model_version_from_db", lambda *a, **k: None)
    monkeypatch.setattr(index, "worker_client", Worker(post=httpx.ConnectError(SECRET, request=Mock())))
    with pytest.raises(HTTPException) as exc:
        await call_predict()
    assert exc.value.status_code == 503
    assert "10.0.13.7" not in exc.value.detail


@pytest.mark.asyncio
async def test_worker_server_error_body_is_not_forwarded(monkeypatch):
    monkeypatch.setattr(
        index, "worker_client", Worker(post=response(500, {"detail": f"Traceback ... {SECRET}"}, text=SECRET))
    )
    reply = await call_predict()
    assert reply.status_code == 500
    assert b"10.0.13.7" not in reply.body


@pytest.mark.asyncio
async def test_worker_client_error_is_still_passed_through(monkeypatch):
    monkeypatch.setattr(index, "worker_client", Worker(post=response(422, {"detail": "feature 'age' is required"})))
    reply = await call_predict()
    assert reply.status_code == 422
    assert b"age" in reply.body


@pytest.mark.asyncio
async def test_health_failures_do_not_expose_worker_output_or_exception_text(monkeypatch):
    token = {"model_record": dict(RECORD)}
    monkeypatch.setattr(index, "worker_client", Worker(get=response(500, text=SECRET)))
    reply = await index.model_health("v", token)
    assert reply.status_code == 500 and b"10.0.13.7" not in reply.body
    monkeypatch.setattr(index, "worker_client", Worker(get=RuntimeError(SECRET)))
    reply = await index.model_health("v", token)
    assert reply.status_code == 503 and b"10.0.13.7" not in reply.body


@pytest.mark.asyncio
async def test_registry_failure_is_a_generic_503_and_bad_ids_are_404():
    def broken(version_id, redis_client=None):
        raise RuntimeError("postgresql://user:password@db-host/mlops")

    kwargs = dict(
        redis_client=None,
        get_model_version_record=broken,
        verify_project_api_key=None,
        get_public_key=None,
        jwt_module=jwt,
    )
    with pytest.raises(HTTPException) as exc:
        await auth_service.authorize_model_access(VERSION, None, None, **kwargs)
    assert exc.value.status_code == 503
    assert "password" not in exc.value.detail and "db-host" not in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        await auth_service.authorize_model_access("not-a-uuid", None, None, **kwargs)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_invalid_token_response_has_no_decoder_detail():
    record = {"tenant_id": "t", "access_mode": "private", "project_pk": 1}
    with pytest.raises(HTTPException) as exc:
        await auth_service.authorize_model_access(
            VERSION,
            None,
            "Bearer not.a.jwt",
            redis_client=None,
            get_model_version_record=lambda *a, **k: record,
            verify_project_api_key=None,
            get_public_key=None,
            jwt_module=jwt,
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Unauthorized: Invalid token"
