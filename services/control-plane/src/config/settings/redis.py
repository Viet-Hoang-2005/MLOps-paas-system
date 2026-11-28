from urllib.parse import quote, urlsplit, urlunsplit

from django.core.exceptions import ImproperlyConfigured

from common.env import env

REDIS_PASSWORD = env("REDIS_PASSWORD", "")


def _inject_redis_password(url: str, password: str) -> str:
    if not url or not password:
        return url
    parsed = urlsplit(url)
    if parsed.password:
        return url
    username = parsed.username or ""
    auth = f"{username}:{quote(password, safe='')}@"
    host_port = parsed.netloc.split("@")[-1]
    return urlunsplit((parsed.scheme, f"{auth}{host_port}", parsed.path, parsed.query, parsed.fragment))


def _derive_redis_url(base_url: str, db: int) -> str:
    parsed = urlsplit(base_url)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{db}", parsed.query, parsed.fragment))


REDIS_URL = _inject_redis_password(env("REDIS_URL", "redis://redis-cache:6379/0"), REDIS_PASSWORD)
REDIS_CONNECTION_MODE = env("REDIS_CONNECTION_MODE", "direct")
if REDIS_CONNECTION_MODE not in {"direct", "sentinel"}:
    raise ImproperlyConfigured("REDIS_CONNECTION_MODE must be direct or sentinel")

# 1. Redis Cache Configuration (DB 0)
if REDIS_CONNECTION_MODE == "sentinel":
    REDIS_SENTINEL_PASSWORD = env("REDIS_SENTINEL_PASSWORD", "")
    REDIS_SENTINEL_MASTER_NAME = env("REDIS_SENTINEL_MASTER_NAME", "redis-cache-master")
    REDIS_SENTINELS = []
    for address in env("REDIS_SENTINEL_HOSTS", "").split(","):
        if address.strip():
            host, _, port = address.strip().partition(":")
            REDIS_SENTINELS.append((host, int(port or "26379")))
    if not all((REDIS_PASSWORD, REDIS_SENTINEL_PASSWORD, REDIS_SENTINEL_MASTER_NAME)) or len(REDIS_SENTINELS) < 3:
        raise ImproperlyConfigured("Redis Sentinel requires three hosts, master name and both credentials")
    sentinel_kwargs = {"password": REDIS_SENTINEL_PASSWORD, "socket_timeout": 2}
    DJANGO_REDIS_CONNECTION_FACTORY = "django_redis.pool.SentinelConnectionFactory"
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"redis://{REDIS_SENTINEL_MASTER_NAME}/0",
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.SentinelClient",
                "SENTINELS": REDIS_SENTINELS,
                "SENTINEL_KWARGS": sentinel_kwargs,
                "PASSWORD": REDIS_PASSWORD,
            },
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django_redis.cache.RedisCache", "LOCATION": REDIS_URL}}
