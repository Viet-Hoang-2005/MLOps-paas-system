from unittest.mock import Mock

import pytest

from src import api


def test_sentinel_connection_discovers_master(monkeypatch):
    monkeypatch.setattr(api, "REDIS_CONNECTION_MODE", "sentinel")
    monkeypatch.setenv("REDIS_SENTINEL_HOSTS", "sentinel-0:26379,sentinel-1:26379,sentinel-2:26379")
    monkeypatch.setenv("REDIS_SENTINEL_MASTER_NAME", "mlops-paas-redis")
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
    sentinel.master_for.assert_called_once_with("mlops-paas-redis", db=1, password="redis-password")


def test_sentinel_connection_rejects_missing_credentials(monkeypatch):
    monkeypatch.setattr(api, "REDIS_CONNECTION_MODE", "sentinel")
    monkeypatch.setenv("REDIS_SENTINEL_HOSTS", "sentinel-0,sentinel-1,sentinel-2")
    monkeypatch.setenv("REDIS_SENTINEL_MASTER_NAME", "mlops-paas-redis")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("REDIS_SENTINEL_PASSWORD", "sentinel-password")
    with pytest.raises(ValueError, match="requires three hosts"):
        api._redis_connection()
