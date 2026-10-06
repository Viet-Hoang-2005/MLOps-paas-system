from rest_framework.response import Response

from apps.auth.api.serializers import TenantTokenSerializer
from apps.auth.services.cookies import set_refresh_token_cookie


def create_auth_response(user, extra_data=None, status=200):
    refresh = TenantTokenSerializer.get_token(user)
    data = {
        "access": str(refresh.access_token),
        "tenant_id": user.tenant_id,
        **(extra_data or {}),
    }
    response = Response(data, status=status)
    set_refresh_token_cookie(response, str(refresh))
    return response


def token_payload(user, **extra):
    refresh = TenantTokenSerializer.get_token(user)
    return {
        "access": str(refresh.access_token),
        "tenant_id": user.tenant_id,
        **extra,
    }
