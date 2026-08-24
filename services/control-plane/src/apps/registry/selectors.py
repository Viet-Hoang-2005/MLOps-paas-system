from django.shortcuts import get_object_or_404

from .models import ModelVersion


def versions_for_user(user):
    return ModelVersion.objects.filter(project__owner=user).select_related("project", "source_job")


def version_for_user(user, public_id):
    return get_object_or_404(versions_for_user(user), public_id=public_id)
