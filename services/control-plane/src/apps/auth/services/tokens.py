from apps.auth.api.serializers import TenantTokenSerializer


def token_payload(user, **extra):
    refresh = TenantTokenSerializer.get_token(user)
    return {
        "access": str(refresh.access_token),  # type: ignore[attr-defined]
        "refresh": str(refresh),
        "tenant_id": user.tenant_id,
        **extra,
    }
