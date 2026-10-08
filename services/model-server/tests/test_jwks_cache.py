import asyncio
import time
from unittest.mock import AsyncMock, Mock

import pytest
from src import auth as auth_service
from src.jwks_cache import JwksKeyCache


def test_jwks_cache_set_and_get():
    cache = JwksKeyCache(max_size=10, positive_ttl=3600.0, negative_ttl=60.0)
    cache.set("key-1", "pubkey-1")
    assert cache.get("key-1") == "pubkey-1"
    assert "key-1" in cache
    assert len(cache) == 1
    assert cache.get("non-existent") is None
    assert "non-existent" not in cache


def test_jwks_cache_expiration(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)
    cache = JwksKeyCache(max_size=10, positive_ttl=3600.0, negative_ttl=60.0)
    cache.set("key-1", "pubkey-1")
    assert cache.get("key-1") == "pubkey-1"
    
    now += 3601.0
    assert cache.get("key-1") is None
    assert "key-1" not in cache
    assert len(cache) == 0


def test_jwks_cache_negative_caching(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)
    cache = JwksKeyCache(max_size=10, positive_ttl=3600.0, negative_ttl=60.0)
    cache.set_negative("missing-key")
    assert cache.is_negative("missing-key") is True
    assert cache.get("missing-key") is None
    assert "missing-key" in cache

    now += 61.0
    assert cache.is_negative("missing-key") is False
    assert "missing-key" not in cache


def test_jwks_cache_lru_eviction():
    cache = JwksKeyCache(max_size=3, positive_ttl=3600.0, negative_ttl=60.0)
    cache.set("k1", "v1")
    cache.set("k2", "v2")
    cache.set("k3", "v3")

    # Access k1 to make k2 the LRU
    assert cache.get("k1") == "v1"

    # Add k4 -> should evict k2
    cache.set("k4", "v4")
    assert len(cache) == 3
    assert cache.get("k2") is None
    assert cache.get("k1") == "v1"
    assert cache.get("k3") == "v3"
    assert cache.get("k4") == "v4"


@pytest.mark.asyncio
async def test_fetch_public_key_negative_caching_protects_jwks_endpoint():
    cache = JwksKeyCache(max_size=10, positive_ttl=3600.0, negative_ttl=60.0)
    summary = Mock()
    response = Mock()
    response.json.return_value = {"keys": [{"kid": "real-key", "n": "abc"}]}
    
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = response

    rsa_algo = Mock()
    rsa_algo.from_jwk.return_value = "parsed-real-key"

    # Request bogus key
    key1 = await auth_service.fetch_public_key(
        "bogus-key",
        cache=cache,
        jwks_url="http://jwks",
        summary=summary,
        http_client_factory=lambda: client,
        rsa_algorithm=rsa_algo,
    )
    assert key1 is None
    assert client.get.call_count == 1
    assert cache.is_negative("bogus-key") is True

    # Repeated request for bogus key should hit negative cache directly (0 additional HTTP calls)
    key2 = await auth_service.fetch_public_key(
        "bogus-key",
        cache=cache,
        jwks_url="http://jwks",
        summary=summary,
        http_client_factory=lambda: client,
        rsa_algorithm=rsa_algo,
    )
    assert key2 is None
    assert client.get.call_count == 1  # Still 1! Protected from DoS.


@pytest.mark.asyncio
async def test_fetch_public_key_caches_all_returned_keys():
    cache = JwksKeyCache(max_size=10, positive_ttl=3600.0, negative_ttl=60.0)
    summary = Mock()
    response = Mock()
    response.json.return_value = {
        "keys": [
            {"kid": "key-1", "n": "abc"},
            {"kid": "key-2", "n": "def"},
        ]
    }

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = response

    rsa_algo = Mock()
    rsa_algo.from_jwk.side_effect = lambda payload: f"parsed-{payload}"

    # Fetch key-1
    res1 = await auth_service.fetch_public_key(
        "key-1",
        cache=cache,
        jwks_url="http://jwks",
        summary=summary,
        http_client_factory=lambda: client,
        rsa_algorithm=rsa_algo,
    )
    assert res1 is not None
    assert client.get.call_count == 1

    # Fetch key-2 should hit cache without additional HTTP request
    res2 = await auth_service.fetch_public_key(
        "key-2",
        cache=cache,
        jwks_url="http://jwks",
        summary=summary,
        http_client_factory=lambda: client,
        rsa_algorithm=rsa_algo,
    )
    assert res2 is not None
    assert client.get.call_count == 1  # Still 1!

