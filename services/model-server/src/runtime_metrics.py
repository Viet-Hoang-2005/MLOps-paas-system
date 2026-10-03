"""Local-only, shared gateway counter. No samples or durable metric history."""

import uuid

INCREMENT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    redis.call('HSET', KEYS[1], 'generation', ARGV[1], 'count', 0)
end
redis.call('HINCRBY', KEYS[1], 'count', 1)
redis.call('EXPIRE', KEYS[1], 300)
"""


async def record_request(client, tenant_id, project_id, version_id):
    if client is None:
        return
    try:
        key = f"runtime_requests:{tenant_id}:{project_id}:{version_id}"
        await client.eval(INCREMENT, 1, key, uuid.uuid4().hex)
    except Exception:
        # Observability must never change an inference response or leak Redis details.
        return
