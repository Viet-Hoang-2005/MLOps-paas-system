"""Refresh rotation must consume a refresh token only once, including on failure."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from django.contrib.auth import get_user_model
from django.db import OperationalError, connection, connections
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.auth.api.serializers import TenantTokenSerializer, _KeyIdRefreshToken
from apps.auth.tests.test_auth import browser_auth_headers


def refresh(raw):
    client = APIClient(raise_request_exception=False)
    client.cookies["refresh_token"] = raw
    return client.post("/api/auth/token/refresh/", **browser_auth_headers())


@pytest.mark.django_db
def test_refresh_rejects_token_consumed_between_validation_and_blacklist(monkeypatch):
    user = get_user_model().objects.create_user("refresh-race@example.com")
    raw = str(TenantTokenSerializer.get_token(user))
    blacklist = _KeyIdRefreshToken.blacklist

    def concurrent_consume(token):
        # Model a competing revocation winning after validation but before insert.
        blacklist(token)
        return blacklist(token)

    monkeypatch.setattr(_KeyIdRefreshToken, "blacklist", concurrent_consume)
    response = refresh(raw)
    assert response.status_code in (401, 403)
    assert response.data["error"]["code"] == "token_not_valid"
    assert "access" not in response.data
    assert "refresh_token" not in response.cookies


@pytest.mark.django_db
def test_failed_new_token_persistence_rolls_back_consumption(monkeypatch):
    user = get_user_model().objects.create_user("refresh-rollback@example.com")
    original = TenantTokenSerializer.get_token(user)
    raw = str(original)
    old_jti = original["jti"]
    with monkeypatch.context() as patch:

        def fail_create(*args, **kwargs):
            raise OperationalError("Database unavailable")

        patch.setattr(OutstandingToken.objects, "create", fail_create)
        response = refresh(raw)
    assert response.status_code == 500
    assert "refresh_token" not in response.cookies
    assert not BlacklistedToken.objects.filter(token__jti=old_jti).exists()
    assert refresh(raw).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_concurrent_refresh_same_cookie_succeeds_exactly_once():
    if connection.vendor != "postgresql":
        pytest.skip("Row-lock concurrency requires disposable PostgreSQL.")
    user = get_user_model().objects.create_user("refresh-concurrent@example.com")
    token = TenantTokenSerializer.get_token(user)
    raw = str(token)
    gate = Barrier(2)

    def attempt():
        try:
            gate.wait(timeout=10)
            response = refresh(raw)
            return response.status_code, bool(response.cookies.get("refresh_token")), response.data
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(lambda _: attempt(), range(2)))
    assert sum(status == 200 for status, _, _ in responses) == 1
    rejected = next((status, data) for status, _, data in responses if status != 200)
    assert rejected[0] in (401, 403)
    assert rejected[1]["error"]["code"] == "token_not_valid"
    assert sum(cookie for _, cookie, _ in responses) == 1
    assert BlacklistedToken.objects.filter(token__jti=token["jti"]).count() == 1
    assert OutstandingToken.objects.filter(user=user).count() == 2


@pytest.mark.django_db(transaction=True)
def test_refresh_loses_to_concurrent_revocation(monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("Concurrent revocation requires disposable PostgreSQL.")
    user = get_user_model().objects.create_user("refresh-revocation@example.com")
    token = TenantTokenSerializer.get_token(user)
    raw = str(token)
    before_claim, revoked = Event(), Event()
    blacklist = _KeyIdRefreshToken.blacklist

    def wait_for_revocation(refresh_token):
        before_claim.set()
        if not revoked.wait(timeout=10):
            raise TimeoutError("Concurrent revocation did not finish")
        return blacklist(refresh_token)

    monkeypatch.setattr(_KeyIdRefreshToken, "blacklist", wait_for_revocation)

    def attempt():
        try:
            return refresh(raw)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as workers:
        result = workers.submit(attempt)
        try:
            assert before_claim.wait(timeout=10)
            outstanding = OutstandingToken.objects.get(jti=token["jti"])
            BlacklistedToken.objects.create(token=outstanding)
        finally:
            revoked.set()
        response = result.result(timeout=10)

    assert response.status_code in (401, 403)
    assert response.data["error"]["code"] == "token_not_valid"
    assert "access" not in response.data
    assert "refresh_token" not in response.cookies
    assert OutstandingToken.objects.filter(user=user).count() == 1
    assert BlacklistedToken.objects.filter(token__jti=token["jti"]).exists()
