import requests
from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.deployment.models import Endpoint
from apps.observability.lifecycle import record_registry_event
from apps.registry.models import ModelVersion, RegistryAlias
from infrastructure.http import HttpClient


def predict_alias(*, project, alias_name, payload, http=None):
    alias = RegistryAlias.objects.filter(project=project, name=alias_name).select_related("version").first()
    if not alias:
        raise NotFound("Registry alias does not exist.")
    return predict_version(version=alias.version, payload=payload, http=http)


def predict_version(*, version, payload, http=None):
    endpoint = (
        Endpoint.objects.filter(
            deployment__version=version,
            deployment__active_projects=version.project,
            deployment__status="succeeded",
            deployment__version__project__is_active=True,
            deployment__version__project__deletion_state="active",
        )
        .order_by("-created_at")
        .first()
    )
    if not endpoint:
        raise ValidationError({"version": "The model version has no Running succeeded deployment."})
    try:
        response = (http or HttpClient(timeout=(3.05, 60))).request(
            "POST",
            f"{endpoint.internal_url}/predict",
            json=payload,
        )
    except requests.RequestException as exc:
        from rest_framework.exceptions import APIException

        error = APIException("The model runtime is unavailable.")
        error.status_code = 503
        raise error from exc
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
@transaction.atomic
def set_alias(*, project, actor, name, version):
    from apps.registry.models import RegistryAlias
    from common.api.exceptions import Conflict

    if version.project_id != project.id:
        raise ValidationError({"version": "The version belongs to another project."})
    project = type(project).objects.select_for_update().filter(pk=project.pk, deletion_state="active").first()
    version = ModelVersion.objects.filter(pk=version.pk, deletion_requested=False).first()
    if not project or not version:
        raise Conflict("This project or model version is being deleted.")
    alias, _ = RegistryAlias.objects.update_or_create(project=project, name=name, defaults={"version": version})
    record_registry_event(version=version, actor=actor, event_type="alias_updated", to_state=name)
    return alias
