"""Create Redis clients that follow the current Sentinel master in production."""

from functools import lru_cache

from django.conf import settings
from redis import Redis
from redis.sentinel import Sentinel


@lru_cache(maxsize=3)
def redis_client(db: int = 1) -> Redis:
    if db not in {1, 3, 4}:
        raise ValueError("Unsupported Redis database")
    if settings.REDIS_CONNECTION_MODE == "sentinel":
        sentinel = Sentinel(
            settings.REDIS_SENTINELS,
            sentinel_kwargs={"password": settings.REDIS_SENTINEL_PASSWORD, "socket_timeout": 2},
            socket_timeout=2,
        )
        return sentinel.master_for(
            settings.REDIS_SENTINEL_MASTER_NAME,
            db=db,
            password=settings.REDIS_PASSWORD,
        )
    if db == 1:
        return Redis.from_url(settings.REDIS_URL)
    return Redis.from_url(settings.CELERY_BROKER_URL if db == 3 else settings.CELERY_RESULT_BACKEND)
