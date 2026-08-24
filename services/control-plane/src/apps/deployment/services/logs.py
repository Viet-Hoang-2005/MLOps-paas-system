from collections.abc import Sequence

from django.conf import settings
from django.utils import timezone
from redis import Redis
from redis.exceptions import RedisError

LOG_TTL_SECONDS = 3600


def _decode_logs(lines: Sequence[bytes | str]) -> list[str]:
    return [line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line) for line in lines]


def build_logs(build, offset: int) -> tuple[list[str], int]:
    """Return the live Redis stream for a build, with persisted logs as fallback.

    Model-packager writes one Redis list per immutable model version. Redis is a
    short-lived transport only; ``Build.logs`` remains the durable history once
    the execution task has completed.
    """
    key = f"build_logs:{build.public_id}"
    try:
        redis = Redis.from_url(settings.REDIS_URL)
        lines = redis.lrange(key, offset, -1)
        total = redis.llen(key)
        if total:
            return _decode_logs(lines), total
    except RedisError:
        pass

    persisted = build.logs.splitlines()
    return persisted[offset:], len(persisted)


def deployment_logs(deployment, offset: int) -> tuple[list[str], int]:
    """Return the short-lived deployment progress stream."""
    try:
        redis = Redis.from_url(settings.REDIS_URL)
        key = f"deployment_logs:{deployment.public_id}"
        return _decode_logs(redis.lrange(key, offset, -1)), redis.llen(key)
    except RedisError:
        return [], 0


def reset_deployment_logs(deployment, message: str) -> None:
    try:
        redis = Redis.from_url(settings.REDIS_URL)
        key = f"deployment_logs:{deployment.public_id}"
        redis.delete(key)
        _push_runtime_log(redis, key, message)
    except RedisError:
        pass


def append_deployment_log(deployment, message: str) -> None:
    try:
        redis = Redis.from_url(settings.REDIS_URL)
        _push_runtime_log(redis, f"deployment_logs:{deployment.public_id}", message)
    except RedisError:
        pass


def _push_runtime_log(redis, key: str, message: str) -> None:
    timestamp = timezone.now().strftime("%H:%M:%S")
    redis.rpush(key, f"[{timestamp}] INFO {message}")
    redis.expire(key, LOG_TTL_SECONDS)
