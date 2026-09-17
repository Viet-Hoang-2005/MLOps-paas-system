from infrastructure.http import HttpClient
from rest_framework.exceptions import NotFound, ValidationError

from apps.deployment.models import Endpoint
from apps.registry.models import RegistryAlias


def predict_alias(*, project, alias_name, payload, http=None):
    alias = RegistryAlias.objects.filter(project=project, name=alias_name).select_related("version").first()
    if not alias:
        raise NotFound("Registry alias does not exist.")
    return predict_version(version=alias.version, payload=payload, http=http)


def predict_version(*, version, payload, http=None):
    endpoint = (
        Endpoint.objects.filter(
            deployment__version=version,
            deployment__status="healthy",
            health_status="healthy",
        )
        .order_by("-created_at")
        .first()
    )
    if not endpoint:
        raise ValidationError({"version": "The model version has no healthy endpoint."})
    response = (http or HttpClient(timeout=(3.05, 60))).request(
        "POST",
        f"{endpoint.internal_url}/predict",
        json=payload,
    )
    body = response.json()
    return {
        "success": True,
        "endpoint_url": endpoint.public_url,
        "status_code": response.status_code,
        "prediction_id": body.get("prediction_id") if isinstance(body, dict) else None,
        "prediction": body.get("prediction") if isinstance(body, dict) else None,
        "confidence": body.get("confidence") if isinstance(body, dict) else None,
        "response": body,
    }
