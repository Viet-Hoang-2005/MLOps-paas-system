from .models import UserAPIKey


def active_api_keys(user):
    return UserAPIKey.objects.filter(user=user, revoked_at__isnull=True).prefetch_related("allowed_projects")
