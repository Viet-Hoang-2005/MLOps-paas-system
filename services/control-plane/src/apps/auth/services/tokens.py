from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.auth.api.serializers import TenantTokenSerializer
from apps.auth.services.cookies import set_refresh_token_cookie


def revoke_user_refresh_tokens(user) -> int:
    """
    Revokes (blacklists) all outstanding refresh tokens for the given user,
    invalidating all existing sessions.
    """
    outstanding_tokens = OutstandingToken.objects.filter(user=user).exclude(
        blacklistedtoken__isnull=False
    )
    revoked = 0
    for token in outstanding_tokens:
        BlacklistedToken.objects.get_or_create(token=token)
        revoked += 1
    return revoked


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
