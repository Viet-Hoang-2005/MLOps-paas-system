import logging

from apps.deployment.models import Build
from apps.deployment.serving.health import effective_health
from apps.drift.models import DriftRun
from apps.training.jobs.models import TrainingJob
from infrastructure.telemetry.prometheus import PrometheusClient

logger = logging.getLogger(__name__)


def _safe_prom_query(client, expr):
    try:
        return client.query(expr)
    except Exception as exc:
        logger.warning("Prometheus query failed (%s): %s", type(exc).__name__, expr)
        return []


def model_observability(project, prometheus=None):
    latest_build = Build.objects.filter(project=project).order_by("-created_at").first()
    latest_deployment = project.active_deployment
    endpoint = getattr(latest_deployment, "endpoint", None) if latest_deployment else None
    latest_training = TrainingJob.objects.filter(project=project).order_by("-created_at").first()
    latest_drift = DriftRun.objects.filter(monitor__version__project=project).order_by("-created_at").first()
    metrics_client = prometheus or PrometheusClient()
    tenant_id = getattr(getattr(project, "owner", None), "tenant_id", "")
    scope = f'project_id="{project.public_id}",tenant_id="{tenant_id}"'
    return {
        "project_id": str(project.public_id),
        "build": _resource(latest_build),
        "deployment": _resource(latest_deployment),
        "endpoint": {
            "id": str(endpoint.public_id),
            "health_status": effective_health(endpoint),
            "public_url": endpoint.public_url,
            "last_checked_at": endpoint.last_checked_at,
        }
        if endpoint
        else None,
        "training": _resource(latest_training),
        "drift": _resource(latest_drift),
        "metrics": {
            "requests": _safe_prom_query(metrics_client, f"paas_predictions_total{{{scope}}}"),
            "latency": _safe_prom_query(
                metrics_client,
                f"rate(paas_prediction_latency_seconds_sum{{{scope}}}[5m]) / "
                f"clamp_min(rate(paas_prediction_latency_seconds_count{{{scope}}}[5m]), 1)",
            ),
        },
    }


def _resource(instance):
    if not instance:
        return None
    return {
        "id": str(instance.public_id),
        "status": instance.status,
        "updated_at": getattr(instance, "updated_at", None),
        "error": getattr(instance, "error_message", ""),
    }
