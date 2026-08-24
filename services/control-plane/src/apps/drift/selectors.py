from django.shortcuts import get_object_or_404

from .models import DriftMonitor, DriftRun


def monitors_for_user(user):
    return (
        DriftMonitor.objects.filter(version__project__owner=user)
        .select_related("version", "reference_asset")
        .order_by("-created_at")
    )


def monitor_for_user(user, public_id):
    return get_object_or_404(monitors_for_user(user), public_id=public_id)


def run_for_user(user, public_id):
    return get_object_or_404(DriftRun.objects.filter(monitor__version__project__owner=user), public_id=public_id)
