from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.deployment.models import Deployment
from apps.deployment.services.cache import invalidate_model_server_cache
from apps.deployment.tasks import execute_deployment, stop_deployment
from common.logging import runtime_line
from infrastructure.execution import deployment_backend


def request_deployment(build, backend):
    with transaction.atomic():
        from apps.catalog.models import ModelProject

        project = ModelProject.objects.select_for_update().get(pk=build.project_id)
        if project.deletion_state != "active":
            raise ValidationError({"project": "This project is being deleted."})
        if Deployment.objects.filter(
            version__project=project, status__in=("pending", "deploying", "unconfirmed")
        ).exists():
            from common.api.exceptions import Conflict

            raise Conflict("A deployment is already in progress for this project.")
        build = type(build).objects.select_for_update().get(pk=build.pk)
        if build.status != "ready" or build.version_id is None:
            raise ValidationError({"build": "Only a ready build can be deployed."})
        deployment = Deployment.objects.create(version=build.version, build=build, backend=backend, status="pending")
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
