"""GitHub profile email alone must never establish a local identity."""

import pytest
import requests
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.auth.services.oauth import authenticate_github
from apps.auth.tests.test_auth import browser_auth_headers


class Response:
    def __init__(self, data, *, has_next=False):
        self.data = data
        self.links = {"next": {}} if has_next else {}

    def json(self):
        return self.data


class GitHubClient:
    def __init__(self, pages, profile_email="victim@example.com"):
        self.pages = pages
        self.profile_email = profile_email
        self.email_calls = []

    def request(self, method, url, **kwargs):
        if url == "https://github.com/login/oauth/access_token":
            return Response({"access_token": "provider-token"})
        if url == "https://api.github.com/user":
            return Response({"email": self.profile_email, "name": "GitHub User"})
        if url == "https://api.github.com/user/emails":
            self.email_calls.append(kwargs)
            page = kwargs.get("params", {}).get("page", 1)
            result = self.pages[page - 1]
            if isinstance(result, Exception):
                raise result
            return Response(result, has_next=page < len(self.pages))
        if url == "https://api.github.com/graphql":
            return Response({})
        raise AssertionError("Unexpected GitHub endpoint")


@pytest.fixture
def github_settings(settings):
    settings.GITHUB_OAUTH2_CLIENT_ID = "client-id"
    settings.GITHUB_OAUTH2_CLIENT_SECRET = "client-secret"


@pytest.mark.django_db
@pytest.mark.parametrize("profile_email", ["victim@example.com", None])
def test_github_sign_in_uses_only_verified_primary_email(github_settings, profile_email):
    victim = get_user_model().objects.create_user("victim@example.com")
    owner = get_user_model().objects.create_user("owner@example.com")
    client = GitHubClient([[{"email": owner.email, "primary": True, "verified": True}]], profile_email)

    user, created = authenticate_github("code", "http://localhost/callback", http=client)

    assert created is False
    assert user.pk == owner.pk and user.pk != victim.pk
    assert len(client.email_calls) == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "emails",
    [
        [],
        [{"email": "victim@example.com", "primary": True, "verified": False}],
        [{"email": "victim@example.com", "primary": False, "verified": True}],
        [{"email": "victim@example.com", "primary": "true", "verified": "true"}],
        [{"email": "", "primary": True, "verified": True}],
        {"message": "not authorized"},
    ],
)
def test_github_invalid_email_list_does_not_issue_session(github_settings, monkeypatch, emails):
    victim = get_user_model().objects.create_user("victim@example.com")
    client = GitHubClient([emails])
    monkeypatch.setattr("apps.auth.services.oauth.HttpClient", lambda: client)
    response = APIClient().post(
        "/api/auth/oauth/github/",
        {"code": "code", "redirect_uri": "http://localhost/callback"},
        format="json",
        **browser_auth_headers(),
    )
    assert response.status_code in (401, 403)
    assert "access" not in response.data
    assert "refresh_token" not in response.cookies
    assert list(get_user_model().objects.values_list("pk", flat=True)) == [victim.pk]


@pytest.mark.django_db
def test_github_finds_verified_primary_on_later_page(github_settings):
    client = GitHubClient(
        [
            [{"email": "secondary@example.com", "primary": False, "verified": True}],
            [{"email": "owner@example.com", "primary": True, "verified": True}],
        ]
    )
    user, created = authenticate_github("code", "http://localhost/callback", http=client)
    assert created is True and user.email == "owner@example.com"
    assert [call["params"]["page"] for call in client.email_calls] == [1, 2]


@pytest.mark.django_db
def test_github_verified_primary_issues_browser_session(github_settings, monkeypatch):
    owner = get_user_model().objects.create_user("owner@example.com")
    client = GitHubClient([[{"email": owner.email, "primary": True, "verified": True}]])
    monkeypatch.setattr("apps.auth.services.oauth.HttpClient", lambda: client)
    response = APIClient().post(
        "/api/auth/oauth/github/",
        {"code": "code", "redirect_uri": "http://localhost/callback"},
        format="json",
        **browser_auth_headers(),
    )
    assert response.status_code == 200
    assert response.data["tenant_id"] == owner.tenant_id
    assert "access" in response.data and "refresh" not in response.data
    assert response.cookies["refresh_token"]["httponly"] is True


@pytest.mark.django_db
def test_github_email_pagination_is_bounded(github_settings, monkeypatch):
    client = GitHubClient([[] for _ in range(11)])
    monkeypatch.setattr("apps.auth.services.oauth.HttpClient", lambda: client)
    response = APIClient().post(
        "/api/auth/oauth/github/",
        {"code": "code", "redirect_uri": "http://localhost/callback"},
        format="json",
        **browser_auth_headers(),
    )
    assert response.status_code in (401, 403)
    assert len(client.email_calls) == 10
    assert "refresh_token" not in response.cookies


@pytest.mark.django_db
def test_github_email_api_failure_never_falls_back_to_profile(github_settings, monkeypatch):
    get_user_model().objects.create_user("victim@example.com")
    client = GitHubClient([requests.ConnectionError("provider unavailable")])
    monkeypatch.setattr("apps.auth.services.oauth.HttpClient", lambda: client)
    response = APIClient(raise_request_exception=False).post(
        "/api/auth/oauth/github/",
        {"code": "code", "redirect_uri": "http://localhost/callback"},
        format="json",
        **browser_auth_headers(),
    )
    assert response.status_code >= 400
    assert "refresh_token" not in response.cookies
    assert get_user_model().objects.count() == 1
