import time
from typing import cast

from celery.signals import task_postrun, task_prerun
from django.conf import settings
from prometheus_client import Counter, Histogram
from redis import Redis

API_REQUESTS = Counter(
    "control_plane_api_requests_total",
    "Control-plane HTTP requests.",
    ("method", "route", "status"),
)
API_DURATION = Histogram(
    "control_plane_api_request_duration_seconds",
    "Control-plane HTTP request duration.",
    ("method", "route"),
)
CELERY_TASKS = Counter(
    "control_plane_celery_tasks_total",
    "Control-plane Celery task outcomes.",
    ("task", "status"),
)
CELERY_DURATION = Histogram(
    "control_plane_celery_task_duration_seconds",
    "Control-plane Celery task duration.",
    ("task",),
)


@task_prerun.connect
def record_task_start(task_id=None, task=None, **kwargs):
    if task is not None:
        task.request._metrics_started_at = time.monotonic()


@task_postrun.connect
def record_task_complete(task_id=None, task=None, state=None, **kwargs):
    if task is None:
        return
    name = task.name or "unknown"
    started_at = getattr(task.request, "_metrics_started_at", None)
    if started_at is not None:
        duration = time.monotonic() - started_at
        CELERY_DURATION.labels(task=name).observe(duration)
    else:
        duration = 0
    status = (state or "unknown").lower()
    CELERY_TASKS.labels(task=name, status=status).inc()
    try:
        redis = Redis.from_url(settings.REDIS_URL)
        redis.hincrby("metrics:celery:tasks", f"{name}|{status}", 1)
        redis.hincrbyfloat("metrics:celery:duration_seconds", name, duration)
        redis.hincrby("metrics:celery:duration_count", name, 1)
    except Exception:
        pass


def shared_celery_metrics():
    try:
        redis = Redis.from_url(settings.REDIS_URL)
        task_totals = cast(dict[bytes, bytes], redis.hgetall("metrics:celery:tasks"))
        duration_totals = cast(dict[bytes, bytes], redis.hgetall("metrics:celery:duration_seconds"))
        duration_counts = cast(dict[bytes, bytes], redis.hgetall("metrics:celery:duration_count"))
        lines = [
            "# TYPE control_plane_celery_queue_depth gauge",
            f"control_plane_celery_queue_depth {redis.llen('celery')}",
        ]
        lines.append("# TYPE control_plane_celery_shared_tasks_total counter")
        for raw_key, raw_value in task_totals.items():
            task_name, status = raw_key.decode().rsplit("|", 1)
            lines.append(
                f'control_plane_celery_shared_tasks_total{{task="{task_name}",status="{status}"}} {raw_value.decode()}'
            )
        lines.append("# TYPE control_plane_celery_shared_duration_seconds_total counter")
        for raw_name, raw_value in duration_totals.items():
            task_name = raw_name.decode()
            lines.append(
                f'control_plane_celery_shared_duration_seconds_total{{task="{task_name}"}} {raw_value.decode()}'
            )
            count = duration_counts.get(raw_name, b"0").decode()
            lines.append(f'control_plane_celery_shared_duration_seconds_count{{task="{task_name}"}} {count}')
        return ("\n".join(lines) + "\n").encode()
    except Exception:
        return b""
