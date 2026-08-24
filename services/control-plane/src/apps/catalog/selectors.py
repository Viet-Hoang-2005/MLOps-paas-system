from django.shortcuts import get_object_or_404

from .models import ModelProject


def project_for_user(user, public_id, *, include_inactive=False):
    queryset = ModelProject.objects.filter(owner=user)
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return get_object_or_404(queryset, public_id=public_id)
