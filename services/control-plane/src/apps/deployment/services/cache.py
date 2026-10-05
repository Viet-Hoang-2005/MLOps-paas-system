import logging
from typing import Optional

from redis.exceptions import RedisError

from common.redis_client import redis_client

logger = logging.getLogger(__name__)


def invalidate_model_server_cache(version_public_id: Optional[str]) -> bool:
    """Invalidate the model-server routing cache in Redis (database 1).

    This ensures that when a deployment succeeds, is stopped, or fails,
    the gateway (model-server) immediately clears its cached routing record
    rather than waiting for the 30-second TTL to expire.
    """
    if not version_public_id:
        return False
    try:
        client = redis_client()
        cache_key = f"model-version:{version_public_id}"
        deleted = client.delete(cache_key)
        if deleted:
            logger.info("Invalidated model-server cache for version %s", version_public_id)
        return bool(deleted)
    except RedisError as exc:
        logger.warning(
            "Failed to invalidate model-server Redis cache for %s: %s",
            version_public_id,
            exc,
        )
        return False
