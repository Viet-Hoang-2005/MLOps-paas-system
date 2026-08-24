from infrastructure.prometheus import PrometheusClient

from apps.deployment.models import Build, Deployment, Endpoint
from apps.drift.models import DriftRun
from apps.training.models import TrainingJob


def model_observability(project, prometheus=None):
    latest_build = Build.objects.filter(project=project).order_by("-created_at").first()
    latest_deployment = Deployment.objects.filter(version__project=project).order_by("-created_at").first()
    endpoint = Endpoint.objects.filter(deployment__version__project=project).order_by("-created_at").first()
    latest_training = TrainingJob.objects.filter(project=project).order_by("-created_at").first()
    latest_drift = DriftRun.objects.filter(monitor__version__project=project).order_by("-created_at").first()
    metrics_client = prometheus or PrometheusClient()
    return {
        "project_id": str(project.public_id),
        "build": _resource(latest_build),
        "deployment": _resource(latest_deployment),
        "endpoint": {
            "id": str(endpoint.public_id),
            "health_status": endpoint.health_status,
            "public_url": endpoint.public_url,
            "last_checked_at": endpoint.last_checked_at,
        }
        if endpoint
        else None,
        "training": _resource(latest_training),
        "drift": _resource(latest_drift),
        "metrics": {
            "requests": metrics_client.query(
                f'paas_predictions_total{{project_id="{project.public_id}"}}'
            ),
            "latency": metrics_client.query(
                f'paas_prediction_latency_seconds_count{{project_id="{project.public_id}"}}'
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
