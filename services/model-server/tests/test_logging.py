from unittest.mock import AsyncMock, Mock
import logging

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from src.logging_utils import current_context
from src.logging_utils import RequestLoggingMiddleware

from src import api as index, database


def test_gateway_installs_request_logging():
    middleware = next(
        item for item in index.app.user_middleware if item.cls is RequestLoggingMiddleware
    )
    assert middleware.kwargs["routes"] is index.app.router.routes


def test_publication_summarizes_enqueue_failure_and_recovery_without_payload(monkeypatch):
    summary = Mock()
    producer = Mock()
    producer.produce.side_effect = [RuntimeError("https://private/?token=hidden feature-payload"), None]
    monkeypatch.setattr(index, "publication_summary", summary)
    monkeypatch.setattr(index, "kafka_producer", producer)
    for _ in range(2):
        index.send_to_redpanda("tenant", "project", "version", {"secret": "feature-payload"}, "prediction-payload")

    assert summary.record.call_args_list[0].kwargs["success"] is False
    assert summary.record.call_args_list[1].kwargs["records"] == 1
    summary.failure.assert_called_once_with("publish", "Inference event enqueue failed", error_type="RuntimeError")
    summary.recovery.assert_called_once_with("publish")
    assert "payload" not in str(summary.mock_calls)
    assert "https://" not in str(summary.mock_calls)


def test_missing_producer_is_observable(monkeypatch):
    summary = Mock()
    monkeypatch.setattr(index, "publication_summary", summary)
    monkeypatch.setattr(index, "kafka_producer", None)
    index.send_to_redpanda("t", "p", "v", {}, None)
    summary.record.assert_called_once_with(success=False)
    summary.failure.assert_called_once()


@pytest.mark.asyncio
async def test_jwks_recovery_waits_until_key_parsing_succeeds(monkeypatch):
    summary = Mock()
    response = Mock()
    response.json.return_value = {"keys": [{"kid": "logging-test-key"}]}
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = response
    monkeypatch.setattr(index, "JWKS_CACHE", {})
    monkeypatch.setattr(index, "jwks_summary", summary)
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda: client)
    monkeypatch.setattr(index.RSAAlgorithm, "from_jwk", Mock(side_effect=[ValueError("private-key-payload"), ValueError("private-key-payload"), "public-key"]))
    assert await index.get_public_key("logging-test-key") is None
    assert await index.get_public_key("logging-test-key") is None
    summary.recovery.assert_not_called()
    assert await index.get_public_key("logging-test-key") == "public-key"
    summary.recovery.assert_called_once_with("fetch")
    assert summary.failure.call_count == 2
    assert "private-key-payload" not in str(summary.mock_calls)


def test_cache_invalidation_failure_and_recovery_are_safe(monkeypatch):
    summary = Mock()
    client = Mock()
    client.delete.side_effect = [RuntimeError("redis://user:hidden@host"), 1]
    monkeypatch.setattr(database, "cache_summary", summary)
    assert database.invalidate_model_version_cache("v", client) is False
    assert database.invalidate_model_version_cache("v", client) is True
    summary.failure.assert_called_once_with("invalidate", "Model registry cache invalidation failed", error_type="RuntimeError")
    summary.recovery.assert_called_once_with("invalidate")


@pytest.mark.asyncio
async def test_gateway_shutdown_closes_summaries_even_if_producer_flush_fails(monkeypatch):
    monkeypatch.setattr(index, "configure", Mock())
    producer = Mock()
    producer.flush.side_effect = RuntimeError("flush failed")
    publication, jwks = Mock(), Mock()
    monkeypatch.setattr(index, "create_redis_client", lambda: None)
    monkeypatch.setattr(index, "create_kafka_producer", lambda: producer)
    monkeypatch.setattr(index, "publication_summary", publication)
    monkeypatch.setattr(index, "jwks_summary", jwks)
    with pytest.raises(RuntimeError, match="flush failed"):
        async with index.lifespan(index.app):
            pass
    publication.close.assert_called_once()
    jwks.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("header", [None, "invalid request id", "valid-request-1"])
async def test_prediction_uses_one_validated_id_and_trusted_context(monkeypatch, header):
    response = Mock(status_code=200)
    response.json.return_value = {"prediction": 1}
    observed = []
    client = AsyncMock()
    client.__aenter__.return_value = client

    async def post(*args, **kwargs):
        observed.append(current_context())
        return response

    client.post.side_effect = post
    monkeypatch.setattr(index.httpx, "AsyncClient", lambda **_: client)
    record = {"id": "trusted-version", "project_id": "trusted-project", "tenant_id": "trusted-tenant"}
    headers = [] if header is None else [(b"x-request-id", header.encode())]
    request = Request({"type": "http", "headers": headers})
    tasks = BackgroundTasks()
    before = current_context()
    result = await index.predict("untrusted-route-id", request, index.InferenceRequest(features={"tenant_id": "untrusted-feature"}), tasks, {"model_record": record})
    assert result.status_code == 200
    context = observed[0]
    assert context["tenant_id"] == "trusted-tenant"
    assert context["project_id"] == "trusted-project"
    assert context["model_version_id"] == "trusted-version"
    assert context["request_id"] == tasks.tasks[0].kwargs["request_id"]
    assert client.post.call_args.kwargs["headers"] == {"X-Request-ID": context["request_id"]}
    assert client.post.call_args.kwargs["json"] == {"features": {"tenant_id": "untrusted-feature"}, "model_version_id": "trusted-version"}
    if header == "valid-request-1":
        assert context["request_id"] == header
    else:
        import uuid
        uuid.UUID(context["request_id"])
    assert request.scope["state"]["mlops_log_context"] == context
    assert current_context() == before


@pytest.mark.asyncio
async def test_prediction_resets_context_when_route_resolution_fails(monkeypatch):
    monkeypatch.setattr(index, "resolve_worker_url", Mock(side_effect=HTTPException(503, "unavailable")))
    before = current_context()
    with pytest.raises(HTTPException):
        await index.predict("v", Request({"type": "http", "headers": []}), index.InferenceRequest(features={}), BackgroundTasks(), {"model_record": {"id": "v", "tenant_id": "t", "project_id": "p"}})
    assert current_context() == before


def test_http_failure_keeps_resource_context_after_handler_reset(monkeypatch, caplog):
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_api_route("/models/{version_id}/predict", index.predict, methods=["POST"])
    app.add_middleware(RequestLoggingMiddleware)
    app.dependency_overrides[index.verify_model_access] = lambda: {"model_record": {"id": "trusted-version", "tenant_id": "trusted-tenant", "project_id": "trusted-project"}}
    monkeypatch.setattr(index, "resolve_worker_url", Mock(side_effect=HTTPException(503, "unavailable")))
    caplog.set_level(logging.INFO)
    before = current_context()
    with TestClient(app) as client:
        response = client.post("/models/request-version/predict", json={"features": {"project_id": "untrusted"}}, headers={"X-Request-ID": "request-1"})
    assert response.status_code == 503
    errors = [record for record in caplog.records if getattr(record, "event", "") == "http.request.failed"]
    assert len(errors) == 1
    assert errors[0].tenant_id == "trusted-tenant"
    assert errors[0].project_id == "trusted-project"
    assert errors[0].model_version_id == "trusted-version"
    assert current_context() == before
