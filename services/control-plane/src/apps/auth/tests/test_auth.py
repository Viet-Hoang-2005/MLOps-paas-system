from urllib.parse import urlparse

import jwt
import pytest
from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.core.files.base import ContentFile
from django.test import override_settings
from rest_framework.test import APIClient

from apps.auth.services.oauth import _oauth_user, authenticate_github, authenticate_google


def browser_auth_headers(origin="http://localhost:5173"):
    return {
        "HTTP_X_REQUESTED_WITH": "XMLHttpRequest",
        "HTTP_ORIGIN": origin,
    }


class FakeResponse:
    def __init__(self, payload=None, content=b"", content_type="image/png"):
        self.payload = payload or {}
        self.content = content
        self.headers = {"Content-Type": content_type}

    def json(self):
        return self.payload

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.content


class GoogleOAuthClient:
    def __init__(self, profile, avatar=b"avatar"):
        self.profile = profile
        self.avatar = avatar
        self.urls = []

    def request(self, method, url, **kwargs):
        self.urls.append((method, url, kwargs))
        if "userinfo" in url:
            return FakeResponse(payload=self.profile)
        return FakeResponse(content=self.avatar)


class GitHubOAuthClient:
    def __init__(self):
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        if url == "https://github.com/login/oauth/access_token":
            return FakeResponse(payload={"access_token": "github-token"})
        if url == "https://api.github.com/user":
            return FakeResponse(payload={"email": "github-owner@example.com", "name": "GitHub Owner"})
        if url == "https://api.github.com/graphql":
            return FakeResponse(
                payload={"data": {"viewer": {"avatarUrl": "https://avatars.githubusercontent.com/u/12345?size=512"}}}
            )
        return FakeResponse(content=b"github-avatar")


@pytest.mark.django_db
def test_token_contains_tenant_id_and_sets_cookie():
    user = get_user_model().objects.create_user("owner@example.com", "password123")
    response = APIClient().post(
        "/api/auth/token/",
        {"email": user.email, "password": "password123"},
        format="json",
        **browser_auth_headers(),
    )

    assert response.status_code == 200
    assert response.data["tenant_id"] == user.tenant_id
    assert user.tenant_id == f"T-{user.public_id}"
    assert "access" in response.data
    assert "refresh" not in response.data
    assert "refresh_token" in response.cookies
    cookie = response.cookies["refresh_token"]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/api/auth/"


@pytest.mark.django_db
def test_refreshed_access_token_via_cookie_keeps_gateway_claims():
    user = get_user_model().objects.create_user("refresh@example.com", "password123")
    client = APIClient()
    issued = client.post(
        "/api/auth/token/",
        {"email": user.email, "password": "password123"},
        format="json",
        **browser_auth_headers(),
    )
    assert issued.status_code == 200
    assert "refresh_token" in issued.cookies

    # 1. Missing security header is rejected (403)
    client.cookies["refresh_token"] = issued.cookies["refresh_token"].value
    rejected_no_header = client.post("/api/auth/token/refresh/", format="json")
    assert rejected_no_header.status_code == 403

    # 2. Invalid origin is rejected (403)
    rejected_bad_origin = client.post(
        "/api/auth/token/refresh/",
        format="json",
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        HTTP_ORIGIN="http://malicious-site.com",
    )
    assert rejected_bad_origin.status_code == 403

    rejected_missing_origin = client.post(
        "/api/auth/token/refresh/",
        format="json",
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert rejected_missing_origin.status_code == 403

    rejected_missing_custom_header = client.post(
        "/api/auth/token/refresh/",
        format="json",
        HTTP_ORIGIN="http://localhost:5173",
    )
    assert rejected_missing_custom_header.status_code == 403

    # 3. Valid refresh with cookie and header
    response = client.post(
        "/api/auth/token/refresh/",
        format="json",
        **browser_auth_headers(),
    )
    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" not in response.data
    assert "refresh_token" in response.cookies
    assert jwt.get_unverified_header(response.data["access"])["kid"] == "mlops-paas-key-1"
    claims = jwt.decode(response.data["access"], options={"verify_signature": False})
    assert claims["tenant_id"] == user.tenant_id
    assert claims["aud"] == "mlops-paas"


@pytest.mark.django_db
def test_logout_blacklists_token_and_clears_cookie():
    user = get_user_model().objects.create_user("logout@example.com", "password123")
    client = APIClient()
    issued = client.post(
        "/api/auth/token/",
        {"email": user.email, "password": "password123"},
        format="json",
        **browser_auth_headers(),
    )
    old_refresh = issued.cookies["refresh_token"].value
    client.cookies["refresh_token"] = old_refresh

    # Missing header is rejected
    rejected = client.post("/api/auth/logout/", format="json")
    assert rejected.status_code == 403

    # Logout with header
    logout_res = client.post(
        "/api/auth/logout/",
        format="json",
        **browser_auth_headers(),
    )
    assert logout_res.status_code == 200
    assert logout_res.cookies["refresh_token"].value == ""

    # Re-using the logged-out refresh token fails (token was blacklisted)
    client.cookies["refresh_token"] = old_refresh
    retry_refresh = client.post(
        "/api/auth/token/refresh/",
        format="json",
        **browser_auth_headers(),
    )
    assert retry_refresh.status_code in (401, 403)


@pytest.mark.django_db
def test_logout_invalid_refresh_cookie_is_idempotent_and_cleared():
    client = APIClient()
    client.cookies["refresh_token"] = "not-a-valid-refresh-token"

    response = client.post("/api/auth/logout/", format="json", **browser_auth_headers())

    assert response.status_code == 200
    assert response.cookies["refresh_token"].value == ""


@pytest.mark.django_db
def test_legacy_profile_me_route_is_not_available():
    response = APIClient().get("/api/auth/profile/me/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_complete_registration_ignores_field_of_work(monkeypatch):
    monkeypatch.setattr(
        "apps.auth.api.registration_endpoints.read_token",
        lambda token, purpose: {"email": "new-owner@example.com"},
    )

    response = APIClient().post(
        "/api/auth/register/complete/",
        {
            "registration_token": "registration-token",
            "full_name": "New Owner",
            "password": "ValidStrongPass#2026",
            "field_of_work": "Must be ignored during registration",
        },
        format="json",
        **browser_auth_headers(),
    )

    assert response.status_code == 201
    assert "access" in response.data
    assert "refresh" not in response.data
    assert "refresh_token" in response.cookies
    assert response.cookies["refresh_token"]["httponly"] is True
    user = get_user_model().objects.get(email="new-owner@example.com")
    assert user.full_name == "New Owner"
    assert user.field_of_work == ""


@pytest.mark.django_db
def test_cookie_issuing_endpoints_reject_missing_browser_security_headers(monkeypatch):
    user = get_user_model().objects.create_user("csrf@example.com", "password123")
    client = APIClient()

    login = client.post(
        "/api/auth/token/",
        {"email": user.email, "password": "password123"},
        format="json",
        HTTP_ORIGIN="http://localhost:5173",
    )
    assert login.status_code == 403

    oauth = client.post(
        "/api/auth/oauth/google/",
        {"token": "provider-token"},
        format="json",
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )
    assert oauth.status_code == 403

    monkeypatch.setattr(
        "apps.auth.api.registration_endpoints.read_token",
        lambda token, purpose: {"email": "csrf-registration@example.com"},
    )
    registration = client.post(
        "/api/auth/register/complete/",
        {
            "registration_token": "registration-token",
            "full_name": "CSRF Test",
            "password": "password123",
        },
        format="json",
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        HTTP_ORIGIN="http://malicious-site.example",
    )
    assert registration.status_code == 403
    assert not get_user_model().objects.filter(email="csrf-registration@example.com").exists()


@pytest.mark.django_db
def test_google_oauth_endpoint_sets_refresh_cookie(monkeypatch):
    user = get_user_model().objects.create_user("oauth-cookie@example.com", "password123")
    monkeypatch.setattr(
        "apps.auth.api.oauth_endpoints.authenticate_google",
        lambda token: (user, False),
    )

    response = APIClient().post(
        "/api/auth/oauth/google/",
        {"token": "provider-token"},
        format="json",
        **browser_auth_headers(),
    )

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" not in response.data
    assert response.cookies["refresh_token"]["httponly"] is True


@pytest.mark.django_db
def test_logout_blacklist_database_error_is_not_reported_as_success(monkeypatch):
    user = get_user_model().objects.create_user("logout-error@example.com", "password123")
    client = APIClient(raise_request_exception=False)
    issued = client.post(
        "/api/auth/token/",
        {"email": user.email, "password": "password123"},
        format="json",
        **browser_auth_headers(),
    )
    client.cookies["refresh_token"] = issued.cookies["refresh_token"].value

    def fail_blacklist(_self):
        raise OperationalError("blacklist storage unavailable")

    monkeypatch.setattr("apps.auth.api.endpoints._KeyIdRefreshToken.blacklist", fail_blacklist)
    response = client.post("/api/auth/logout/", format="json", **browser_auth_headers())
    assert response.status_code == 500


@pytest.mark.django_db
@override_settings(GOOGLE_OAUTH2_CLIENT_ID="test-google-client")
def test_google_oauth_saves_provider_avatar_and_profile_exposes_provider():
    client = GoogleOAuthClient(
        {
            "email": "google-owner@example.com",
            "email_verified": True,
            "name": "Google Owner",
            "picture": "https://lh3.googleusercontent.com/a/avatar=s512-c",
        }
    )

    user, created = authenticate_google("google-token", http=client)

    assert created is True
    assert user.auth_provider == "google"
    assert user.avatar.name.endswith("oauth-google.png")
    assert user.avatar_history.count() == 1
    assert any(url.endswith("=s512-c") for _, url, _ in client.urls)

    _, second_login_created = authenticate_google("google-token", http=client)

    assert second_login_created is False
    assert sum("googleusercontent.com" in url for _, url, _ in client.urls) == 1

    api_client = APIClient()
    api_client.force_authenticate(user)
    response = api_client.get("/api/auth/profile/")

    assert response.status_code == 200
    assert response.data["auth_provider"] == "google"
    assert urlparse(response.data["avatar"]).path.endswith("oauth-google.png")


@pytest.mark.django_db
def test_oauth_does_not_replace_an_existing_avatar():
    user = get_user_model().objects.create_user("existing@example.com", "password123")
    user.avatar.save("custom.png", ContentFile(b"custom"), save=True)
    client = GoogleOAuthClient({}, avatar=b"provider-avatar")

    returned, created = _oauth_user(
        user.email,
        "Existing User",
        "google",
        avatar_url="https://lh3.googleusercontent.com/a/avatar",
        http=client,
    )

    assert created is False
    assert returned.avatar.name.endswith("custom.png")
    assert len(client.urls) == 0


@pytest.mark.django_db
@override_settings(GOOGLE_OAUTH2_CLIENT_ID="test-google-client")
def test_google_oauth_does_not_restore_a_removed_avatar():
    user = get_user_model().objects.create_user(
        "removed@example.com",
        "password123",
        auth_provider="google",
    )
    client = GoogleOAuthClient(
        {
            "email": user.email,
            "email_verified": True,
            "name": "Removed Avatar User",
            "picture": "https://lh3.googleusercontent.com/a/avatar=s512-c",
        }
    )

    returned, created = authenticate_google("google-token", http=client)

    assert created is False
    assert not returned.avatar
    assert [url for _, url, _ in client.urls] == ["https://www.googleapis.com/oauth2/v3/userinfo"]


@pytest.mark.django_db
def test_github_avatar_is_saved_only_when_oauth_creates_the_account():
    client = GoogleOAuthClient({}, avatar=b"github-avatar")

    user, created = _oauth_user(
        "github-owner@example.com",
        "GitHub Owner",
        "github",
        avatar_url="https://avatars.githubusercontent.com/u/12345",
        http=client,
    )

    assert created is True
    assert user.avatar.name.endswith("oauth-github.png")
    assert [url for _, url, _ in client.urls] == ["https://avatars.githubusercontent.com/u/12345"]


@pytest.mark.django_db
@override_settings(GITHUB_OAUTH2_CLIENT_ID="test-github-client", GITHUB_OAUTH2_CLIENT_SECRET="test-github-secret")
def test_github_oauth_requests_and_saves_a_512_pixel_avatar():
    client = GitHubOAuthClient()

    user, created = authenticate_github("github-code", "http://localhost:5173/oauth/github/callback", http=client)

    assert created is True
    assert user.avatar.name.endswith("oauth-github.png")
    graphql_request = next(request for request in client.requests if request[1] == "https://api.github.com/graphql")
    assert "avatarUrl(size: 512)" in graphql_request[2]["json"]["query"]
    assert any(url.endswith("?size=512") for _, url, _ in client.requests)


@pytest.mark.django_db
def test_oauth_avatar_rejects_untrusted_url_without_failing_login():
    client = GoogleOAuthClient({}, avatar=b"provider-avatar")

    user, created = _oauth_user(
        "safe@example.com",
        "Safe User",
        "google",
        avatar_url="https://example.invalid/avatar.png",
        http=client,
    )

    assert created is True
    assert not user.avatar
    assert len(client.urls) == 0
