"""Create Redis clients for Cache and Queue instances, following Sentinel master in production."""

from functools import lru_cache

from django.conf import settings
from redis import Redis
from redis.sentinel import Sentinel


@lru_cache(maxsize=8)
def redis_client(db: int | str = 0) -> Redis:
    """Return a Redis client for the requested purpose/database.

    Routes db in {0, 1, 'cache'} to the Cache instance (DB 0).
    Routes db in {3, 'broker', 'queue'} to the Celery Broker queue instance (DB 0).
    Routes db in {4, 'result'} to the Celery Result backend queue instance (DB 0).
    """
    is_queue = db in {3, 4, "queue", "broker", "result"}
    is_cache = db in {0, 1, "cache"}
    if not (is_queue or is_cache):
        raise ValueError("Unsupported Redis database or purpose")

    if is_queue:
        celery_mode = getattr(settings, "CELERY_CONNECTION_MODE", getattr(settings, "REDIS_CONNECTION_MODE", "direct"))
        if celery_mode == "sentinel":
            sentinels = getattr(settings, "CELERY_SENTINELS", getattr(settings, "REDIS_SENTINELS", []))
            sentinel_password = getattr(
                settings, "CELERY_SENTINEL_PASSWORD", getattr(settings, "REDIS_SENTINEL_PASSWORD", "")
            )
            master_name = getattr(
                settings, "CELERY_SENTINEL_MASTER_NAME", getattr(settings, "REDIS_SENTINEL_MASTER_NAME", "redis-queue-master")
            )
            sentinel = Sentinel(
                sentinels,
                sentinel_kwargs={"password": sentinel_password, "socket_timeout": 2},
                socket_timeout=2,
            )
            return sentinel.master_for(
                master_name,
                db=0,
                password=settings.REDIS_PASSWORD,
            )
        url = settings.CELERY_RESULT_BACKEND if (db in {4, "result"} and hasattr(settings, "CELERY_RESULT_BACKEND")) else settings.CELERY_BROKER_URL
        return Redis.from_url(url)

    # Cache instance
    if getattr(settings, "REDIS_CONNECTION_MODE", "direct") == "sentinel" and getattr(settings, "REDIS_SENTINELS", None):
        sentinel = Sentinel(
            settings.REDIS_SENTINELS,
            sentinel_kwargs={"password": settings.REDIS_SENTINEL_PASSWORD, "socket_timeout": 2},
            socket_timeout=2,
        )
        return sentinel.master_for(
            settings.REDIS_SENTINEL_MASTER_NAME,
            db=0,
            password=settings.REDIS_PASSWORD,
        )
    return Redis.from_url(settings.REDIS_URL)


def get_redis_cache_client() -> Redis:
    """Convenience helper for cache client."""
    return redis_client(0)


def get_redis_queue_client() -> Redis:
    """Convenience helper for queue client."""
    return redis_client(3)
