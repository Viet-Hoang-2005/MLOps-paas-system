"""Refresh rotation must consume a refresh token only once, including on failure."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import OperationalError, connection, connections
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.auth.api.serializers import TenantTokenSerializer, _KeyIdRefreshToken
from apps.auth.services import passwords
from apps.auth.tests.test_auth import browser_auth_headers


def refresh(raw):
    client = APIClient(raise_request_exception=False)
    client.cookies["refresh_token"] = raw
    return client.post("/api/auth/token/refresh/", **browser_auth_headers())


def verification_token(user, purpose):
    return signing.dumps({"email": user.email, "purpose": purpose, "jti": uuid4().hex}, salt="identity-otp")


@pytest.mark.django_db
@pytest.mark.parametrize("purpose", ["password_reset", "password_change"])
def test_password_update_rolls_back_on_blacklist_failure(monkeypatch, purpose):
    user = get_user_model().objects.create_user("password-rollback@example.com", "Original#2026")
    raw = str(TenantTokenSerializer.get_token(user))
    token = verification_token(user, purpose)
    actor = user if purpose == "password_change" else None
    revoke = passwords.revoke_user_refresh_tokens

    def fail_after_blacklisting(account):
        revoke(account)
        raise OperationalError("Simulated blacklist failure")

    with monkeypatch.context() as patch:
        patch.setattr(passwords, "revoke_user_refresh_tokens", fail_after_blacklisting)
        with pytest.raises(OperationalError):
            passwords.complete_password_update(token, "Different#2026", actor=actor)

    user.refresh_from_db()
    assert user.check_password("Original#2026")
    assert user.session_version == 0
    assert refresh(raw).status_code == 200
    assert passwords.complete_password_update(token, "Different#2026", actor=actor).status_code == 200


@pytest.mark.django_db
def test_refresh_from_stale_account_state_is_rejected_even_without_blacklist_entry():
    user = get_user_model().objects.create_user("password-stale-session@example.com", "Original#2026")
    token = verification_token(user, "password_reset")
    assert passwords.complete_password_update(token, "Different#2026").status_code == 200

    stale = TenantTokenSerializer.get_token(user)
    assert "session_version" not in stale.access_token
    assert not BlacklistedToken.objects.filter(token__jti=stale["jti"]).exists()
    response = refresh(str(stale))
    assert response.status_code in (401, 403)
    assert response.data["error"]["code"] == "token_not_valid"


@pytest.mark.django_db(transaction=True)
def test_password_reset_revokes_concurrently_rotated_session(monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("Row-lock concurrency requires disposable PostgreSQL.")
    user = get_user_model().objects.create_user("password-refresh-race@example.com", "Original#2026")
    raw = str(TenantTokenSerializer.get_token(user))
    token = verification_token(user, "password_reset")
    rotating, resetting = Event(), Event()
    claim = _KeyIdRefreshToken.blacklist

    def claim_during_reset(refresh_token):
        rotating.set()
        if not resetting.wait(timeout=10):
            raise TimeoutError("Password reset did not start")
        return claim(refresh_token)

    monkeypatch.setattr(_KeyIdRefreshToken, "blacklist", claim_during_reset)

    def rotate():
        try:
            return refresh(raw)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as workers:
        rotation = workers.submit(rotate)
        try:
            assert rotating.wait(timeout=10)
        finally:
            resetting.set()
        assert passwords.complete_password_update(token, "Different#2026").status_code == 200
        rotated = rotation.result(timeout=10)

    assert rotated.status_code == 200
    assert refresh(rotated.cookies["refresh_token"].value).status_code in (401, 403)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {rotated.data['access']}")
    assert client.get("/api/auth/profile/").status_code == 200


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
