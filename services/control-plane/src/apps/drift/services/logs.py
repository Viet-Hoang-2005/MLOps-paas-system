from collections.abc import Sequence

from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError

from common.logging import runtime_line


def _decode_logs(lines: Sequence[bytes | str]) -> list[str]:
    return [runtime_line(line) for line in lines]


def drift_run_logs(run, offset: int) -> tuple[list[str], int]:
    """Read Evidently's transient Redis stream for an authorized drift run."""
    try:
        redis = Redis.from_url(settings.REDIS_URL)
        key = f"drift_logs:{run.public_id}"
        return _decode_logs(redis.lrange(key, offset, -1)), redis.llen(key)
    except RedisError:
        return [], 0
