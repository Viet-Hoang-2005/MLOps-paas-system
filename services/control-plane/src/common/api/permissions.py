import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class IsTenantMember(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)


class HasInternalWebhookSecret(BasePermission):
    message = "Invalid internal webhook secret."

    def has_permission(self, request, view):
        expected = settings.CONTROL_PLANE_WEBHOOK_SECRET
        authorization = request.headers.get("Authorization", "")
        bearer = authorization[7:] if authorization.startswith("Bearer ") else ""
        supplied = request.headers.get("X-Control-Plane-Secret") or bearer
        return bool(expected and supplied and hmac.compare_digest(expected, supplied))
