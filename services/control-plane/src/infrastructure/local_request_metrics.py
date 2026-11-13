"""Read one short-lived local gateway counter with bounded Redis IO."""

from django.conf import settings
from redis import Redis


class LocalRequestCounterClient:
    def read(self, *, tenant_id, project_id, version_id):
        key = f"runtime_requests:{tenant_id}:{project_id}:{version_id}"
        with Redis.from_url(settings.REDIS_URL, socket_timeout=0.2, socket_connect_timeout=0.2) as client:
            return client.hgetall(key)
