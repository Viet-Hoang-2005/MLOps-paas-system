from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.deployment.models import Deployment
from apps.deployment.services.cache import invalidate_model_server_cache
from apps.deployment.tasks import execute_deployment, stop_deployment
from common.logging import runtime_line
from infrastructure.execution import deployment_backend


def request_deployment(version, target, backend):
    from apps.catalog.models import ModelProject
    if target not in {"staging", "production"}:
        raise ValidationError({"target": "Choose staging or production."})
    with transaction.atomic():
        project = ModelProject.objects.select_for_update().get(pk=version.project_id)
        version = type(version).objects.select_for_update().get(pk=version.pk)
        if not version.artifacts.filter(kind="image").exists():
            raise ValidationError({"version": "Only versions with an immutable image can be deployed."})
        if Deployment.objects.filter(project=project, target=target, status__in=("pending", "deploying", "healthy")).exists():
            raise ValidationError({"target": f"An active {target} deployment already exists for this project."})
        build = version.builds.filter(status="ready").order_by("-created_at").first()
        deployment = Deployment.objects.create(
            project=project, version=version, build=build, target=target, backend=backend, status="pending"
        )
    transaction.on_commit(lambda: _enqueue(deployment))
    return deployment


def _enqueue(deployment):
    result = execute_deployment.delay(str(deployment.public_id))
    Deployment.objects.filter(pk=deployment.pk).update(celery_task_id=result.id)


def request_stop(deployment):
    invalidate_model_server_cache(str(deployment.version.public_id))
    transaction.on_commit(lambda: stop_deployment.delay(str(deployment.public_id)))
    return deployment


def endpoint_logs(endpoint):
    output = deployment_backend(endpoint.deployment.backend).logs(endpoint.deployment)
    return "\n".join(runtime_line(line) for line in output.splitlines())
