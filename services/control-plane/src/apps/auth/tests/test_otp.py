import pytest
from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.core.cache import cache
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.auth.services.otp import (
    MAX_OTP_ATTEMPTS,
    _cache_key,
    read_token,
    send_otp,
    verify_otp,
)


@pytest.fixture(autouse=True)
def clear_otp_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_registration_otp_request_rejects_existing_account():
    get_user_model().objects.create_user("existing@example.com", "password123")
    client = APIClient()

    # 1. Existing email returns 400
    res_existing = client.post(
        "/api/auth/register/request-otp/",
        {"email": "existing@example.com"},
        format="json",
    )
    assert res_existing.status_code == 400
    assert "already exists" in str(res_existing.data)
    assert len(mail.outbox) == 0

    # 2. Non-existing email succeeds with 200
    res_new = client.post(
        "/api/auth/register/request-otp/",
        {"email": "brandnew@example.com"},
        format="json",
    )
    assert res_new.status_code == 200
    assert res_new.data["email"] == "brandnew@example.com"
    assert "Verification code sent." in res_new.data["message"]
    assert len(mail.outbox) == 1
    assert "registration code" in mail.outbox[0].subject.lower()


@pytest.mark.django_db
def test_otp_cooldown_throttles_rapid_requests():
    client = APIClient()
    email = "throttle-test@example.com"

    # First request succeeds (200)
    res1 = client.post("/api/auth/register/request-otp/", {"email": email}, format="json")
    assert res1.status_code == 200

    # Immediate second request is throttled (429)
    res2 = client.post("/api/auth/register/request-otp/", {"email": email}, format="json")
    assert res2.status_code == 429
    assert "Please wait" in str(res2.data)


@pytest.mark.django_db
def test_password_reset_request_throttles_non_existent_email_consistently():
    client = APIClient()
    email = "ghost@example.com"

    # First request
    res1 = client.post("/api/auth/password-reset/request-otp/", {"email": email}, format="json")
    assert res1.status_code == 200

    # Immediate second request
    res2 = client.post("/api/auth/password-reset/request-otp/", {"email": email}, format="json")
    assert res2.status_code == 429


@pytest.mark.django_db
def test_otp_verification_attempts_limit_invalidates_code():
    email = "bruteforce@example.com"
    send_otp(email=email, purpose="registration")
    correct_code = cache.get(_cache_key(email, "registration"))
    assert correct_code is not None

    # Failed attempts 1 to 4
    for _i in range(1, MAX_OTP_ATTEMPTS):
        with pytest.raises(ValidationError) as exc:
            verify_otp(email=email, code="000000", purpose="registration")
        assert "attempt" in str(exc.value)

    # 5th failed attempt burns the code
    with pytest.raises(ValidationError) as exc:
        verify_otp(email=email, code="000000", purpose="registration")
    assert "Too many failed attempts" in str(exc.value)

    # Subsequent attempt even with the correct code fails because it was deleted
    with pytest.raises(ValidationError) as exc:
        verify_otp(email=email, code=correct_code, purpose="registration")
    assert "Invalid or expired" in str(exc.value)


@pytest.mark.django_db
def test_successful_otp_verification_burns_code_immediately():
    email = "onetime@example.com"
    send_otp(email=email, purpose="registration")
    code = cache.get(_cache_key(email, "registration"))
    assert code is not None

    token = verify_otp(email=email, code=code, purpose="registration")
    payload = read_token(token, "registration")
    assert payload["email"] == email

    # Replaying the same code fails immediately
    with pytest.raises(ValidationError) as exc:
        verify_otp(email=email, code=code, purpose="registration")
    assert "Invalid or expired" in str(exc.value)


@pytest.mark.django_db
def test_verification_token_single_use_prevents_replay():
    email = "token-replay@example.com"
    send_otp(email=email, purpose="password_reset")
    code = cache.get(_cache_key(email, "password_reset"))
    token = verify_otp(email=email, code=code, purpose="password_reset")

    # First consumption succeeds
    payload = read_token(token, "password_reset")
    assert payload["email"] == email
    assert "jti" in payload

    # Replaying the same verification token fails
    with pytest.raises(ValidationError) as exc:
        read_token(token, "password_reset")
    assert "already been used" in str(exc.value)


@pytest.mark.django_db
def test_verification_token_consume_false_preserves_token():
    email = "token-peek@example.com"
    send_otp(email=email, purpose="registration")
    code = cache.get(_cache_key(email, "registration"))
    token = verify_otp(email=email, code=code, purpose="registration")

    # Peeking without consuming succeeds
    payload = read_token(token, "registration", consume=False)
    assert payload["email"] == email

    # Consuming subsequently succeeds
    consumed_payload = read_token(token, "registration", consume=True)
    assert consumed_payload["email"] == email

    # Subsequent consumption or peeking fails
    with pytest.raises(ValidationError) as exc:
        read_token(token, "registration", consume=False)
    assert "already been used" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        read_token(token, "registration", consume=True)
    assert "already been used" in str(exc.value)


@pytest.mark.django_db
def test_verification_token_missing_jti_is_rejected():
    legacy_token = signing.dumps(
        {"email": "legacy@example.com", "purpose": "registration"},
        salt="identity-otp",
    )
    with pytest.raises(ValidationError) as exc:
        read_token(legacy_token, "registration")
    assert "Invalid verification token format" in str(exc.value)


@pytest.mark.django_db
def test_password_reset_complete_validates_password_before_consuming_token():
    user = get_user_model().objects.create_user("reset-test@example.com", "oldpassword123")
    send_otp(email=user.email, purpose="password_reset")
    code = cache.get(_cache_key(user.email, "password_reset"))
    token = verify_otp(email=user.email, code=code, purpose="password_reset")

    client = APIClient()

    # 1. Invalid short password -> fails validation, but does NOT consume the token
    short_res = client.post(
        "/api/auth/password-reset/complete/",
        {"reset_token": token, "new_password": "short"},
        format="json",
    )
    assert short_res.status_code == 400
    assert "new_password" in str(short_res.data)

    # 2. Resubmitting with valid password using the same token succeeds
    valid_res = client.post(
        "/api/auth/password-reset/complete/",
        {"reset_token": token, "new_password": "newpassword123"},
        format="json",
    )
    assert valid_res.status_code == 200
    assert valid_res.data["message"] == "Password reset completed."

    # Verify password was actually updated
    user.refresh_from_db()
    assert user.check_password("newpassword123")

    # 3. Attempting to replay the consumed token fails
    replay_res = client.post(
        "/api/auth/password-reset/complete/",
        {"reset_token": token, "new_password": "ValidStrongPass#2026!"},
        format="json",
    )
    assert replay_res.status_code == 400
    assert "already been used" in str(replay_res.data)


@pytest.mark.django_db
def test_password_reset_enforces_numeric_password_validator():
    user = get_user_model().objects.create_user("validator-test@example.com", "OldValidPass#2026!")
    send_otp(email=user.email, purpose="password_reset")
    code = cache.get(_cache_key(user.email, "password_reset"))
    token = verify_otp(email=user.email, code=code, purpose="password_reset")

    client = APIClient()

    # Entirely numeric password should be rejected by NumericPasswordValidator
    res = client.post(
        "/api/auth/password-reset/complete/",
        {"reset_token": token, "new_password": "123456789"},
        format="json",
    )
    assert res.status_code == 400
    assert "numeric" in str(res.data).lower()

    # Verification token remains unconsumed and usable
    valid_res = client.post(
        "/api/auth/password-reset/complete/",
        {"reset_token": token, "new_password": "ValidStrongPass#2026!"},
        format="json",
    )
    assert valid_res.status_code == 200
    assert valid_res.data["message"] == "Password reset completed."


@pytest.mark.django_db
def test_common_passwords_are_allowed_without_common_validator():
    user = get_user_model().objects.create_user("common-ok@example.com", "OldValidPass#2026!")
    send_otp(email=user.email, purpose="password_reset")
    code = cache.get(_cache_key(user.email, "password_reset"))
    token = verify_otp(email=user.email, code=code, purpose="password_reset")

    client = APIClient()
    # "password123" is accepted now that CommonPasswordValidator is removed
    res = client.post(
        "/api/auth/password-reset/complete/",
        {"reset_token": token, "new_password": "password123"},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["message"] == "Password reset completed."


@pytest.mark.django_db
def test_password_reset_revokes_existing_refresh_tokens():
    from apps.auth.tests.test_auth import browser_auth_headers

    user = get_user_model().objects.create_user("revoke-reset@example.com", "InitialPass#2026!")
    client = APIClient()

    # 1. User logs in to obtain a refresh token
    login_res = client.post(
        "/api/auth/token/",
        {"email": user.email, "password": "InitialPass#2026!"},
        format="json",
        **browser_auth_headers(),
    )
    assert login_res.status_code == 200
    old_refresh_cookie = login_res.cookies["refresh_token"].value

    # Verify refresh works before reset
    client.cookies["refresh_token"] = old_refresh_cookie
    refreshed = client.post("/api/auth/token/refresh/", format="json", **browser_auth_headers())
    assert refreshed.status_code == 200
    active_refresh_cookie = refreshed.cookies["refresh_token"].value

    # 2. Complete password reset
    send_otp(email=user.email, purpose="password_reset")
    code = cache.get(_cache_key(user.email, "password_reset"))
    token = verify_otp(email=user.email, code=code, purpose="password_reset")

    reset_res = client.post(
        "/api/auth/password-reset/complete/",
        {"reset_token": token, "new_password": "NewStrongPass#2026!"},
        format="json",
    )
    assert reset_res.status_code == 200

    # 3. Old refresh tokens must now be blacklisted
    client.cookies["refresh_token"] = active_refresh_cookie
    failed_refresh = client.post("/api/auth/token/refresh/", format="json", **browser_auth_headers())
    assert failed_refresh.status_code in (401, 403)
    assert "blacklisted" in str(failed_refresh.data).lower()


@pytest.mark.django_db
def test_password_change_enforces_validators_and_revokes_old_refresh_tokens():
    from apps.auth.tests.test_auth import browser_auth_headers

    user = get_user_model().objects.create_user("change-pw@example.com", "InitialPass#2026!")
    client = APIClient()

    # 1. Login to obtain credentials
    login_res = client.post(
        "/api/auth/token/",
        {"email": user.email, "password": "InitialPass#2026!"},
        format="json",
        **browser_auth_headers(),
    )
    assert login_res.status_code == 200
    access_token = login_res.data["access"]
    old_refresh_cookie = login_res.cookies["refresh_token"].value

    # 2. Request OTP and verify for password_change
    send_otp(email=user.email, purpose="password_change")
    code = cache.get(_cache_key(user.email, "password_change"))
    change_token = verify_otp(email=user.email, code=code, purpose="password_change")

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    # 3. Numeric password fails validation
    weak_res = client.post(
        "/api/auth/profile/change-password/",
        {"password_change_token": change_token, "new_password": "123456789"},
        format="json",
        **browser_auth_headers(),
    )
    assert weak_res.status_code == 400
    assert "numeric" in str(weak_res.data).lower()

    # 4. Valid new password succeeds and sets new session cookie
    success_res = client.post(
        "/api/auth/profile/change-password/",
        {"password_change_token": change_token, "new_password": "ChangedPass#2026!"},
        format="json",
        **browser_auth_headers(),
    )
    assert success_res.status_code == 200
    assert "access" in success_res.data
    new_refresh_cookie = success_res.cookies["refresh_token"].value
    assert new_refresh_cookie != old_refresh_cookie

    # 5. Old refresh token is revoked
    client.credentials()  # clear bearer header
    client.cookies["refresh_token"] = old_refresh_cookie
    old_refresh_attempt = client.post("/api/auth/token/refresh/", format="json", **browser_auth_headers())
    assert old_refresh_attempt.status_code in (401, 403)
    assert "blacklisted" in str(old_refresh_attempt.data).lower()

    # 6. New refresh token is active and valid
    client.cookies["refresh_token"] = new_refresh_cookie
    new_refresh_attempt = client.post("/api/auth/token/refresh/", format="json", **browser_auth_headers())
    assert new_refresh_attempt.status_code == 200
    assert "access" in new_refresh_attempt.data


@pytest.mark.django_db
def test_parallel_failed_otp_verifications_cannot_exceed_max_attempts():
    from concurrent.futures import ThreadPoolExecutor

    email = "parallel-brute@example.com"
    send_otp(email=email, purpose="registration")
    correct_code = cache.get(_cache_key(email, "registration"))
    assert correct_code is not None

    def try_verify(i):
        try:
            verify_otp(email=email, code=f"{i:06d}", purpose="registration")
            return "success"
        except ValidationError as exc:
            msg = str(exc)
            if "Too many failed attempts" in msg:
                return "too_many"
            if "Invalid verification code" in msg:
                return "invalid"
            if "Invalid or expired" in msg:
                return "expired"
            return f"other: {msg}"

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(try_verify, range(1, 16)))

    assert "success" not in results
    invalid_counts = [r for r in results if r == "invalid"]
    assert len(invalid_counts) <= MAX_OTP_ATTEMPTS - 1
    assert all(r in ("invalid", "too_many", "expired") for r in results)
    assert cache.get(_cache_key(email, "registration")) is None


@pytest.mark.django_db
def test_concurrent_correct_otp_verification_only_succeeds_once():
    from concurrent.futures import ThreadPoolExecutor

    email = "parallel-correct@example.com"
    send_otp(email=email, purpose="registration")
    correct_code = cache.get(_cache_key(email, "registration"))
    assert correct_code is not None

    def try_verify(_):
        try:
            return verify_otp(email=email, code=correct_code, purpose="registration")
        except ValidationError:
            return None

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(try_verify, range(5)))

    successful = [r for r in results if r is not None]
    assert len(successful) == 1
    assert cache.get(_cache_key(email, "registration")) is None


@pytest.mark.django_db
def test_password_reset_endpoints_rate_throttled():
    client = APIClient()

    # 1. Password reset complete endpoint throttles after 10 requests
    for _ in range(10):
        res = client.post(
            "/api/auth/password-reset/complete/",
            {"reset_token": "dummy-token", "new_password": "NewPass#2026!"},
            format="json",
        )
        assert res.status_code == 400

    res_throttled = client.post(
        "/api/auth/password-reset/complete/",
        {"reset_token": "dummy-token", "new_password": "NewPass#2026!"},
        format="json",
    )
    assert res_throttled.status_code == 429
    assert "throttled" in str(res_throttled.data).lower()

