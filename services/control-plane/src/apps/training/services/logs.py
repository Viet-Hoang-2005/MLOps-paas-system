from collections.abc import Sequence

from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError

LOG_TTL_SECONDS = 3600


def _decode(lines: Sequence[bytes | str]) -> list[str]:
    return [line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line) for line in lines]


def training_logs(job, offset: int) -> tuple[list[str], int]:
    try:
        redis = Redis.from_url(settings.REDIS_URL)
        key = f"training_logs:{job.public_id}"
        lines = redis.lrange(key, offset, -1)
        total = redis.llen(key)
        if total:
            return _decode(lines), total
    except RedisError:
        pass
    persisted = str(job.tracking.get("logs_tail") or job.error_message or "").splitlines()
    return persisted[offset:], len(persisted)


def append_training_log(job_id, message: str) -> None:
    try:
        redis = Redis.from_url(settings.REDIS_URL)
        key = f"training_logs:{job_id}"
        redis.rpush(key, message)
        redis.expire(key, LOG_TTL_SECONDS)
    except RedisError:
        return


def delete_training_logs(job_id) -> None:
    try:
        Redis.from_url(settings.REDIS_URL).delete(f"training_logs:{job_id}")
    except RedisError:
        return
