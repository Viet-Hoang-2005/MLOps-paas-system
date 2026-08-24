from urllib.parse import urlparse

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import override_settings
from rest_framework.test import APIClient

from apps.auth.services.oauth import _oauth_user, authenticate_github, authenticate_google


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
def test_token_contains_tenant_id():
    user = get_user_model().objects.create_user("owner@example.com", "password123")
    response = APIClient().post(
        "/api/auth/token/",
        {"email": user.email, "password": "password123"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["tenant_id"] == user.tenant_id
    assert user.tenant_id == f"T-{user.public_id}"


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
            "password": "password123",
            "field_of_work": "Must be ignored during registration",
        },
        format="json",
    )

    assert response.status_code == 201
    user = get_user_model().objects.get(email="new-owner@example.com")
    assert user.full_name == "New Owner"
    assert user.field_of_work == ""


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
