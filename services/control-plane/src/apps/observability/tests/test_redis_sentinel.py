from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from common.redis_client import redis_client


class RedisSentinelClientTests(SimpleTestCase):
    def tearDown(self):
        redis_client.cache_clear()
        super().tearDown()

    @override_settings(REDIS_CONNECTION_MODE="direct", REDIS_URL="redis://local:6379/1", CELERY_BROKER_URL="redis://local:6379/3")
    @patch("common.redis_client.Redis.from_url")
    def test_direct_mode_uses_separate_database_for_celery_queue(self, from_url):
        redis_client.cache_clear()
        redis_client(db=3)
        from_url.assert_called_once_with("redis://local:6379/3")

    @override_settings(
        REDIS_CONNECTION_MODE="sentinel",
        REDIS_SENTINELS=[("sentinel-0", 26379), ("sentinel-1", 26379), ("sentinel-2", 26379)],
        REDIS_SENTINEL_MASTER_NAME="mlops-paas-redis",
        REDIS_PASSWORD="redis-password",
        REDIS_SENTINEL_PASSWORD="sentinel-password",
    )
    @patch("common.redis_client.Sentinel")
    def test_sentinel_mode_discovers_master_with_separate_credentials(self, sentinel_class):
        redis_client.cache_clear()
        sentinel_class.return_value.master_for.return_value = Mock()
        redis_client(db=1)
        sentinel_class.assert_called_once_with(
            [("sentinel-0", 26379), ("sentinel-1", 26379), ("sentinel-2", 26379)],
            sentinel_kwargs={"password": "sentinel-password", "socket_timeout": 2},
            socket_timeout=2,
        )
        sentinel_class.return_value.master_for.assert_called_once_with(
            "mlops-paas-redis", db=1, password="redis-password"
        )
