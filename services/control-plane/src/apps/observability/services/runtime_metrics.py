from django.utils import timezone
from rest_framework.exceptions import ValidationError

from infrastructure.prometheus import PrometheusClient
from infrastructure.docker_metrics import DockerMetricsClient
from infrastructure.local_request_metrics import LocalRequestCounterClient

RANGES = {"15m": 900, "1h": 3600, "24h": 86400}


def runtime_metrics(project, *, window="1h", prometheus=None, docker=None, redis=None):
    deployment = project.active_deployment
    if (deployment and deployment.backend == "docker") or (not deployment and _local_backend()):
        return _realtime_metrics(project, deployment, docker=docker, redis=redis)
    if window not in RANGES:
        raise ValidationError({"window": "Choose 15m, 1h or 24h."})
    deployment = project.active_deployment
    empty = {
        "deployment_id": str(deployment.public_id) if deployment else None,
        "status": "unavailable",
        "series": {},
        "window": window,
        "mode": "history",
    }
    client = prometheus or PrometheusClient()
    if not deployment or not client.enabled:
        return empty
    end = timezone.now().timestamp()
    duration = RANGES[window]
    start = max(end - duration, deployment.deployed_at.timestamp() if deployment.deployed_at else end - duration)
    scope = f'container_label_mlops_deployment_id="{deployment.public_id}",container_label_mlops_tenant_id="{project.owner.tenant_id}"'
    request_scope = f'project_id="{project.public_id}",model_version_id="{deployment.version.public_id}",tenant_id="{project.owner.tenant_id}"'
    expressions = {
        "cpu": f"sum(rate(container_cpu_usage_seconds_total{{{scope}}}[1m]))",
        "memory": f"sum(container_memory_working_set_bytes{{{scope}}}) / 1048576",
        "requests": f"sum(rate(paas_predictions_total{{{request_scope}}}[1m]))",
    }
    try:
        series = {
            key: client.query_range(expression, start=start, end=end, step=max(15, duration // 300))
            for key, expression in expressions.items()
        }
    except Exception:
        return empty
    return {**empty, "status": "available" if any(series.values()) else "no_data", "series": series}


def _local_backend():
    from django.conf import settings

    return settings.DEPLOYMENT_BACKEND == "docker"


def _realtime_metrics(project, deployment, *, docker=None, redis=None):
    result = {
        "mode": "realtime",
        "status": "unavailable",
        "deployment_id": str(deployment.public_id) if deployment else None,
        "snapshot": None,
    }
    if not deployment or not project.is_active or project.deletion_state != "active":
        return result
    try:
        sample = (docker or DockerMetricsClient()).sample(deployment)
    except Exception:
        # Docker exceptions may contain host paths/configuration: don't return them.
        return result
    if sample is None:
        return result
    counter = None
    try:
        values = (redis or LocalRequestCounterClient()).read(
            tenant_id=project.owner.tenant_id,
            project_id=project.public_id,
            version_id=deployment.version.public_id,
        )
        if values:
            decoded = {
                (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
                for k, v in values.items()
            }
            count = int(decoded["count"])
            if count >= 0 and decoded.get("generation"):
                counter = {"count": count, "generation": decoded["generation"]}
    except Exception:
        pass
    return {
        **result,
        "status": "available" if any(value is not None for value in sample.values()) else "no_data",
        "snapshot": {"timestamp": timezone.now().timestamp(), **sample, "request_counter": counter},
    }
