from django.shortcuts import get_object_or_404

from .models import TrainingJob


def jobs_for_user(user):
    return TrainingJob.objects.filter(project__owner=user).select_related("project")


def job_for_user(user, public_id):
    return get_object_or_404(jobs_for_user(user), public_id=public_id)
