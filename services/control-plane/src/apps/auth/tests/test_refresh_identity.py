"""Refresh must authorize the current account before issuing either token."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.auth.api.serializers import TenantTokenSerializer
from apps.auth.tests.test_auth import browser_auth_headers


@pytest.mark.django_db
@pytest.mark.parametrize("rotation", [True, False])
@pytest.mark.parametrize("account_state", ["inactive", "soft_deleted", "deleted"])
def test_refresh_rejects_disabled_or_deleted_account(settings, rotation, account_state):
    settings.SIMPLE_JWT = {**settings.SIMPLE_JWT, "ROTATE_REFRESH_TOKENS": rotation}
    user = get_user_model().objects.create_user("refresh-account@example.com")
    token = TenantTokenSerializer.get_token(user)
    raw_refresh = str(token)
    if account_state == "inactive":
        user.is_active = False
        user.save(update_fields=["is_active"])
    elif account_state == "soft_deleted":
        user.soft_delete()
    else:
        user.delete()

    outstanding_count = OutstandingToken.objects.count()
    blacklist_count = BlacklistedToken.objects.count()
    client = APIClient()
    client.cookies["refresh_token"] = raw_refresh
    response = client.post("/api/auth/token/refresh/", **browser_auth_headers())

    assert response.status_code in (401, 403)
    assert response.data["error"]["code"] == "token_not_valid"
    assert "access" not in response.data
    assert "refresh_token" not in response.cookies
    assert OutstandingToken.objects.count() == outstanding_count
    assert BlacklistedToken.objects.count() == blacklist_count


@pytest.mark.django_db
@pytest.mark.parametrize("identity", ["missing", "malformed", "unknown", "wrong_tenant"])
def test_refresh_rejects_invalid_account_binding(identity):
    user = get_user_model().objects.create_user("refresh-binding@example.com")
    token = TenantTokenSerializer.get_token(user)
    if identity == "missing":
        del token[api_settings.USER_ID_CLAIM]
    elif identity == "malformed":
        token[api_settings.USER_ID_CLAIM] = "not-an-integer"
    elif identity == "unknown":
        token[api_settings.USER_ID_CLAIM] = user.pk + 1000
    else:
        token["tenant_id"] = "another-tenant"

    client = APIClient()
    client.cookies["refresh_token"] = str(token)
    response = client.post("/api/auth/token/refresh/", **browser_auth_headers())
    assert response.status_code in (401, 403)
    assert response.data["error"]["code"] == "token_not_valid"
    assert "access" not in response.data
    assert "refresh_token" not in response.cookies
