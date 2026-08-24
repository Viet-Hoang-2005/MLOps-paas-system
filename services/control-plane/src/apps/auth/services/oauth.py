import logging
import re
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from infrastructure.http import HttpClient
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from apps.auth.models import UserAvatar

logger = logging.getLogger(__name__)

MAX_OAUTH_AVATAR_BYTES = 5 * 1024 * 1024
OAUTH_AVATAR_SIZE = 512
OAUTH_AVATAR_HOSTS = {
    "google": ("googleusercontent.com",),
    "github": ("avatars.githubusercontent.com",),
}
CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def authenticate_google(access_token, http=None):
    if not settings.GOOGLE_OAUTH2_CLIENT_ID:
        raise ValidationError({"google": "Google OAuth is not configured."})
    response = (http or HttpClient()).request(
        "GET",
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    profile = response.json()
    email = profile.get("email")
    if not email or not profile.get("email_verified"):
        raise AuthenticationFailed("Google account email is not verified.")
    return _oauth_user(
        email,
        profile.get("name", ""),
        "google",
        avatar_url=_google_avatar_url(profile.get("picture", "")),
        http=http,
    )


def authenticate_github(code, redirect_uri, http=None):
    if not settings.GITHUB_OAUTH2_CLIENT_ID or not settings.GITHUB_OAUTH2_CLIENT_SECRET:
        raise ValidationError({"github": "GitHub OAuth is not configured."})
    client = http or HttpClient()
    token = (
        client.request(
            "POST",
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": settings.GITHUB_OAUTH2_CLIENT_ID,
                "client_secret": settings.GITHUB_OAUTH2_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        .json()
        .get("access_token")
    )
    if not token:
        raise AuthenticationFailed("GitHub did not return an access token.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    profile = client.request("GET", "https://api.github.com/user", headers=headers).json()
    email = profile.get("email")
    if not email:
        emails = client.request("GET", "https://api.github.com/user/emails", headers=headers).json()
        email = next((item["email"] for item in emails if item.get("primary") and item.get("verified")), None)
    if not email:
        raise AuthenticationFailed("GitHub account has no verified primary email.")
    user, created = _oauth_user(email, profile.get("name") or profile.get("login", ""), "github")
    if created:
        avatar_url = _github_avatar_url(token, client)
        if avatar_url:
            _save_oauth_avatar(user, "github", avatar_url, http=client)
    return user, created


def _oauth_user(email, full_name, provider, avatar_url="", http=None):
    user, created = get_user_model().objects.get_or_create(
        email__iexact=email,
        defaults={"email": email, "full_name": full_name, "auth_provider": provider},
    )
    if not user.is_active:
        raise AuthenticationFailed("Account is disabled.")
    if created and avatar_url:
        _save_oauth_avatar(user, provider, avatar_url, http=http)
    return user, created


def _google_avatar_url(avatar_url):
    avatar_url = str(avatar_url)
    sized_url = re.sub(r"=s\d+(?:-[a-z]+)*$", f"=s{OAUTH_AVATAR_SIZE}-c", avatar_url)
    return sized_url if sized_url != avatar_url else f"{avatar_url}=s{OAUTH_AVATAR_SIZE}-c"


def _github_avatar_url(access_token, http):
    try:
        response = http.request(
            "POST",
            "https://api.github.com/graphql",
            json={"query": f"query {{ viewer {{ avatarUrl(size: {OAUTH_AVATAR_SIZE}) }} }}"},
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        )
        return response.json().get("data", {}).get("viewer", {}).get("avatarUrl", "")
    except Exception:  # Avatar synchronization must never block a successful OAuth login.
        logger.warning("Unable to request a sized GitHub avatar", exc_info=True)
        return ""


def _save_oauth_avatar(user, provider, avatar_url, http=None):
    """Copy a provider avatar into our storage without making login depend on it."""
    parsed = urlparse(str(avatar_url))
    allowed_hosts = OAUTH_AVATAR_HOSTS.get(provider, ())
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not any(host == item or host.endswith(f".{item}") for item in allowed_hosts):
        logger.warning("Ignoring OAuth avatar URL with an untrusted host for provider %s", provider)
        return

    try:
        response = (http or HttpClient()).request(
            "GET",
            avatar_url,
            headers={"Accept": "image/*"},
            stream=True,
            allow_redirects=False,
        )
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        extension = CONTENT_TYPE_EXTENSIONS.get(content_type)
        if not extension:
            logger.warning("Ignoring unsupported OAuth avatar content type for provider %s", provider)
            return

        content = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            content.extend(chunk)
            if len(content) > MAX_OAUTH_AVATAR_BYTES:
                logger.warning("Ignoring oversized OAuth avatar for provider %s", provider)
                return
        if not content:
            return

        filename = f"oauth-{provider}{extension}"
        user.avatar.save(filename, ContentFile(bytes(content)), save=True)
        UserAvatar.objects.create(user=user, image=user.avatar.name)
    except Exception:  # Avatar synchronization must never block a successful OAuth login.
        logger.warning("Unable to synchronize OAuth avatar for provider %s", provider, exc_info=True)
