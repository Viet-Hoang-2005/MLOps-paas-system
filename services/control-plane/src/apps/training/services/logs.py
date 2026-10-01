import logging
from collections.abc import Sequence

from django.conf import settings
from redis.exceptions import RedisError

from common.logging import runtime_line
from common.redis_client import redis_client
from infrastructure.runtime_logs import emit_tenant_log, uses_loki

LOG_TTL_SECONDS = 3600
logger = logging.getLogger("control_plane.training")


def _decode(lines: Sequence[bytes | str]) -> list[str]:
    return [runtime_line(line) for line in lines]


def training_logs(job, offset: int) -> tuple[list[str], int]:
    try:
        redis = redis_client()
        key = f"training_logs:{job.public_id}"
        lines = redis.lrange(key, offset, -1)
        total = redis.llen(key)
        if total:
            return _decode(lines), total
    except RedisError:
        pass
    persisted = str(job.tracking.get("logs_tail") or job.error_message or "").splitlines()
    return _decode(persisted[offset:]), len(persisted)


def append_training_log(job_id, message: str) -> None:
    emit_tenant_log(logger, "training", job_id, message)
    # Jobs record TRAINING_BACKEND at creation, so this matches the reader's job.backend check.
    if uses_loki(settings.TRAINING_BACKEND):
        return
    try:
        redis = redis_client()
        key = f"training_logs:{job_id}"
        redis.rpush(key, runtime_line(message))
        redis.expire(key, LOG_TTL_SECONDS)
    except RedisError:
        return


def delete_training_logs(job_id) -> None:
    try:
        redis_client().delete(f"training_logs:{job_id}")
    except RedisError:
        return
