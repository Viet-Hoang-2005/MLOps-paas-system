from django.shortcuts import get_object_or_404

from apps.deployment.models import Build


def builds_for_user(user):
    return (
        Build.objects.filter(project__owner=user).select_related("project", "version").prefetch_related("input_assets")
    )


def build_for_user(user, public_id):
    return get_object_or_404(builds_for_user(user), public_id=public_id)
