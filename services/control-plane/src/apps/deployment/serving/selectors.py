from django.shortcuts import get_object_or_404

from apps.deployment.models import Deployment, Endpoint


def deployments_for_user(user):
    return Deployment.objects.filter(version__project__owner=user).select_related("version", "build")


def deployment_for_user(user, public_id):
    return get_object_or_404(deployments_for_user(user), public_id=public_id)


def endpoints_for_user(user):
    return Endpoint.objects.filter(deployment__version__project__owner=user).select_related(
        "deployment", "deployment__version"
    )


def endpoint_for_user(user, public_id):
    return get_object_or_404(endpoints_for_user(user), public_id=public_id)
