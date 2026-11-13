import json

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from infrastructure.docker_metrics import DockerMetricsClient
from infrastructure.local_request_metrics import LocalRequestCounterClient
from infrastructure.prometheus import PrometheusClient

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
    namespace = json.dumps(settings.MODEL_RUNTIME_NAMESPACE)
    # cAdvisor exposes namespace/pod/container, not Docker container_label_*.
    # Join the explicit KSM allowlist; deduplicate exporter/scrape replicas.
    labels = {
        "namespace": settings.MODEL_RUNTIME_NAMESPACE,
        "label_mlops_io_deployment_id": str(deployment.public_id),
        "label_mlops_io_tenant_id": str(project.owner.tenant_id),
        "label_mlops_io_project_id": str(project.public_id),
        "label_mlops_io_model_version_id": str(deployment.version.public_id),
    }
    scope = ",".join(f"{key}={json.dumps(value)}" for key, value in labels.items())
    owned_pods = f"max by (namespace,pod) (kube_pod_labels{{{scope}}})"
    container_scope = f'namespace={namespace},container="model-server",job="kubelet",metrics_path="/metrics/cadvisor"'
    join = f"* on (namespace,pod) group_left() ({owned_pods})"
    request_scope = f'project_id="{project.public_id}",model_version_id="{deployment.version.public_id}",tenant_id="{project.owner.tenant_id}"'
    expressions = {
        "cpu": f"sum(max by (namespace,pod,container) (rate(container_cpu_usage_seconds_total{{{container_scope}}}[2m])) {join})",
        "memory": f"sum(max by (namespace,pod,container) (container_memory_working_set_bytes{{{container_scope}}}) {join}) / 1048576",
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
