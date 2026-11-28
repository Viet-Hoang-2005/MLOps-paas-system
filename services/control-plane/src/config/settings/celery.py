from urllib.parse import quote

from django.core.exceptions import ImproperlyConfigured

from common.env import env, env_int

from .execution import (
    ACCOUNT_DELETION_PURGE_INTERVAL_SECONDS,
    ARGO_RECONCILE_WEBHOOK_URL,
    DELETION_RECONCILE_INTERVAL_SECONDS,
    DRIFT_EXECUTION_WATCH_ENABLED,
    LOCAL_DEPLOYMENT_WATCH_ENABLED,
    LOCAL_EXECUTION_POLL_SECONDS,
    RUNTIME_HEALTH_INTERVAL_SECONDS,
    STOP_RECONCILE_INTERVAL_SECONDS,
    TRAINING_EXECUTION_WATCH_ENABLED,
)
from .redis import REDIS_CONNECTION_MODE, REDIS_PASSWORD, _inject_redis_password

CELERY_CONNECTION_MODE = env("CELERY_CONNECTION_MODE", REDIS_CONNECTION_MODE)
if CELERY_CONNECTION_MODE not in {"direct", "sentinel"}:
    raise ImproperlyConfigured("CELERY_CONNECTION_MODE must be direct or sentinel")

# 2. Celery Queue Configuration (DB 0)
if CELERY_CONNECTION_MODE == "sentinel":
    CELERY_SENTINEL_PASSWORD = env("CELERY_SENTINEL_PASSWORD", env("REDIS_SENTINEL_PASSWORD", ""))
    CELERY_SENTINEL_MASTER_NAME = env("CELERY_SENTINEL_MASTER_NAME", "redis-queue-master")
    CELERY_SENTINELS = []
    raw_celery_hosts = env("CELERY_SENTINEL_HOSTS", env("REDIS_SENTINEL_HOSTS", ""))
    for address in raw_celery_hosts.split(","):
        if address.strip():
            host, _, port = address.strip().partition(":")
            CELERY_SENTINELS.append((host, int(port or "26379")))
    if not all((REDIS_PASSWORD, CELERY_SENTINEL_PASSWORD, CELERY_SENTINEL_MASTER_NAME)) or len(CELERY_SENTINELS) < 3:
        raise ImproperlyConfigured("Celery Sentinel requires three hosts, master name and both credentials")
    celery_sentinel_kwargs = {"password": CELERY_SENTINEL_PASSWORD, "socket_timeout": 2}

    def _celery_sentinel_urls(db: int = 0) -> str:
        return ";".join(
            f"sentinel://:{quote(REDIS_PASSWORD, safe='')}@{host}:{port}/{db}" for host, port in CELERY_SENTINELS
        )

    CELERY_BROKER_URL = _celery_sentinel_urls(0)
    CELERY_RESULT_BACKEND = _celery_sentinel_urls(0)
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        "master_name": CELERY_SENTINEL_MASTER_NAME,
        "sentinel_kwargs": celery_sentinel_kwargs,
    }
    CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {
        "master_name": CELERY_SENTINEL_MASTER_NAME,
        "sentinel_kwargs": celery_sentinel_kwargs,
    }
else:
    default_queue_url = _inject_redis_password("redis://redis-queue:6379/0", REDIS_PASSWORD)
    CELERY_BROKER_URL = _inject_redis_password(
        env("CELERY_BROKER_URL", default_queue_url),
        REDIS_PASSWORD,
    )
    CELERY_RESULT_BACKEND = _inject_redis_password(
        env("CELERY_RESULT_BACKEND", default_queue_url),
        REDIS_PASSWORD,
    )
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 43200)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 42600)
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

CELERY_TASK_DEFAULT_QUEUE = "celery"

CELERY_TASK_ROUTES = {
    "apps.deployment.health_tasks.scan_runtime_health": {"queue": "runtime-health"},
    "apps.deployment.health_tasks.probe_runtime_health": {"queue": "runtime-health"},
}

CELERY_BEAT_SCHEDULE = {
    "runtime-health-scan": {
        "task": "apps.deployment.health_tasks.scan_runtime_health",
        "schedule": RUNTIME_HEALTH_INTERVAL_SECONDS,
        "options": {"queue": "runtime-health", "expires": 15},
    },
    "stopped-deployment-reconcile": {
        "task": "apps.deployment.tasks.reconcile_stopped_deployments",
        "schedule": STOP_RECONCILE_INTERVAL_SECONDS,
        "options": {"queue": "celery", "expires": 60},
    },
    "stalled-deletion-reconcile": {
        "task": "apps.deployment.tasks.reconcile_stalled_deletions",
        "schedule": DELETION_RECONCILE_INTERVAL_SECONDS,
        "options": {"queue": "celery", "expires": 120},
    },
    "expired-account-purge": {
        "task": "apps.auth.tasks.purge_expired_deleted_accounts",
        "schedule": ACCOUNT_DELETION_PURGE_INTERVAL_SECONDS,
        "options": {"queue": "celery", "expires": 3600},
    },
}
if LOCAL_DEPLOYMENT_WATCH_ENABLED:
    CELERY_BEAT_SCHEDULE["local-execution-scan"] = {
        "task": "apps.deployment.execution_tasks.scan_local_executions",
        "schedule": LOCAL_EXECUTION_POLL_SECONDS,
        "options": {"queue": "celery", "expires": 10},
    }

if DRIFT_EXECUTION_WATCH_ENABLED or TRAINING_EXECUTION_WATCH_ENABLED or ARGO_RECONCILE_WEBHOOK_URL:
    CELERY_BEAT_SCHEDULE["job-execution-scan"] = {
        "task": "apps.observability.tasks.scan_job_executions",
        "schedule": 15,
        "options": {"queue": "celery", "expires": 15},
    }

CELERY_WORKER_HIJACK_ROOT_LOGGER = False
