from unittest.mock import MagicMock, Mock

import httpx
import pytest

from src import api
from src.readiness import dependency_checks


def test_dependency_checks_report_outages_without_secrets():
    engine, redis, producer = MagicMock(), Mock(), Mock()
    producer.list_topics.return_value.brokers = {1: object()}
    assert dependency_checks(engine, lambda: redis, producer) == {"postgres": "ok", "redis": "ok", "kafka": "ok"}
    redis.close.assert_called_once()
    engine.connect.side_effect = RuntimeError("secret database URL")
    redis.ping.side_effect = TimeoutError("secret Redis URL")
    producer.list_topics.side_effect = TimeoutError("secret broker URL")
    assert dependency_checks(engine, lambda: redis, producer) == {"postgres": "unavailable", "redis": "unavailable", "kafka": "unavailable"}
    producer.list_topics.assert_called_with(timeout=2)


@pytest.mark.asyncio
async def test_preflight_and_auth_errors_do_not_require_cookies(monkeypatch):
    monkeypatch.setattr(api, "get_model_version_record", lambda *args, **kwargs: {"tenant_id": "tenant", "access_mode": "private", "project_pk": 1})
    transport = httpx.ASGITransport(app=api.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        url = "/models/00000000-0000-0000-0000-000000000001/predict"
        response = await client.options(url, headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type,x-api-key"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "*"
        assert "access-control-allow-credentials" not in response.headers
        response = await client.post(url, headers={"Origin": "http://localhost:5173"}, json={"data": []})
        assert response.status_code == 401
        assert response.headers["access-control-allow-origin"] == "*"
        assert "access-control-allow-credentials" not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("healthy,code", [(True, 200), (False, 503)])
async def test_gateway_ready_status(monkeypatch, healthy, code):
    monkeypatch.setattr("src.readiness.dependency_checks", lambda *args: {"postgres": "ok", "redis": "ok", "kafka": "ok" if healthy else "unavailable"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://gateway") as client:
        response = await client.get("/health/ready")
    assert response.status_code == code
    assert response.json()["checks"]["kafka"] == ("ok" if healthy else "unavailable")
