"""The broker client must initialize without a server or version mismatch."""

import redis
from kombu.transport.redis import Channel, SentinelChannel


def test_redis_transport_client_supports_installed_redis_version():
    channel = Channel.__new__(Channel)
    assert issubclass(channel._get_client(), redis.Redis)


def test_sentinel_transport_client_supports_installed_redis_version():
    channel = SentinelChannel.__new__(SentinelChannel)
    assert issubclass(channel._get_client(), redis.Redis)
