from unittest.mock import AsyncMock, Mock

import pytest

from src import api


@pytest.mark.parametrize("password", [None, "test-direct-password"])
def test_direct_connection_uses_separate_password_without_changing_url(monkeypatch, password):
    monkeypatch.setattr(api, "REDIS_CONNECTION_MODE", "direct")
    monkeypatch.setattr(api, "REDIS_URL", "redis://cache:6379/0")
    if password:
        monkeypatch.setenv("REDIS_PASSWORD", password)
    else:
        monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    client = api._redis_connection()
    assert client.connection_pool.connection_kwargs.get("password") == password
    assert client.connection_pool.connection_kwargs["host"] == "cache"


def test_direct_connection_preserves_existing_url_credentials(monkeypatch):
    monkeypatch.setattr(api, "REDIS_CONNECTION_MODE", "direct")
    monkeypatch.setattr(api, "REDIS_URL", "redis://:test-url-password@cache:6379/0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    client = api._redis_connection()
    assert client.connection_pool.connection_kwargs["password"] == "test-url-password"


@pytest.mark.asyncio
async def test_async_metrics_connection_receives_separate_password(monkeypatch):
    monkeypatch.setenv("REDIS_PASSWORD", "test-direct-password")
    monkeypatch.setattr(api, "LOCAL_RUNTIME_METRICS_ENABLED", True)
    monkeypatch.setattr(api, "create_redis_client", lambda: None)
    monkeypatch.setattr(api, "create_kafka_producer", lambda: None)
    monkeypatch.setattr(api, "get_worker_client", lambda: None)
    monkeypatch.setattr(api, "worker_client", None)
    client = AsyncMock()
    factory = Mock(return_value=client)
    monkeypatch.setattr(api.async_redis, "from_url", factory)
    async with api.lifespan(api.app):
        assert factory.call_args.kwargs["password"] == "test-direct-password"
    client.aclose.assert_awaited_once()


def test_sentinel_connection_discovers_master(monkeypatch):
    monkeypatch.setattr(api, "REDIS_CONNECTION_MODE", "sentinel")
    monkeypatch.setenv("REDIS_SENTINEL_HOSTS", "sentinel-0:26379,sentinel-1:26379,sentinel-2:26379")
    monkeypatch.setenv("REDIS_SENTINEL_MASTER_NAME", "redis-master")
    monkeypatch.setenv("REDIS_PASSWORD", "redis-password")
    monkeypatch.setenv("REDIS_SENTINEL_PASSWORD", "sentinel-password")
    sentinel = Mock()
    sentinel_class = Mock(return_value=sentinel)
    monkeypatch.setattr(api, "Sentinel", sentinel_class)

    assert api._redis_connection() is sentinel.master_for.return_value
    sentinel_class.assert_called_once_with(
        [("sentinel-0", 26379), ("sentinel-1", 26379), ("sentinel-2", 26379)],
        sentinel_kwargs={"password": "sentinel-password", "socket_timeout": 2},
        socket_timeout=2,
    )
    sentinel.master_for.assert_called_once_with("redis-master", db=0, password="redis-password")


def test_sentinel_connection_rejects_missing_credentials(monkeypatch):
    monkeypatch.setattr(api, "REDIS_CONNECTION_MODE", "sentinel")
    monkeypatch.setenv("REDIS_SENTINEL_HOSTS", "sentinel-0,sentinel-1,sentinel-2")
    monkeypatch.setenv("REDIS_SENTINEL_MASTER_NAME", "redis-master")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("REDIS_SENTINEL_PASSWORD", "sentinel-password")
    with pytest.raises(ValueError, match="requires three hosts"):
        api._redis_connection()
