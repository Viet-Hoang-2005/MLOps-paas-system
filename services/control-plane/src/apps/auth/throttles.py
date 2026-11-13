import hashlib

from rest_framework.throttling import SimpleRateThrottle


class _ScopedThrottle(SimpleRateThrottle):
    """Rate throttle with a settings-driven rate and a safe fallback.

    The client address comes from ``get_ident``: with REST_FRAMEWORK
    ``NUM_PROXIES`` set (``TRUSTED_PROXY_COUNT``) only the entry added by the
    trusted proxies is used, so a client cannot dodge the limit by forging
    ``X-Forwarded-For``.
    """

    default_rate = "10/minute"

    def get_rate(self):
        try:
            return self.THROTTLE_RATES.get(self.scope) or self.default_rate
        except Exception:
            return self.default_rate

    def get_ident_key(self, request) -> str:
        return self.get_ident(request) or "unknown"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident_key(request)}


class PasswordResetRateThrottle(_ScopedThrottle):
    scope = "password_reset"


class RegistrationRateThrottle(_ScopedThrottle):
    scope = "registration"


class PasswordChangeRateThrottle(_ScopedThrottle):
    """Authenticated OTP flow: limit per account, not per address."""

    scope = "password_change"
    default_rate = "10/minute"

    def get_ident_key(self, request) -> str:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return f"user:{user.pk}"
        return super().get_ident_key(request)


class LoginIpRateThrottle(_ScopedThrottle):
    """Caps password guessing from one address, across every account it targets."""

    scope = "login_ip"
    default_rate = "30/minute"


class LoginAccountRateThrottle(_ScopedThrottle):
    """Caps password guessing against one account, whatever addresses it comes from.

    The key is a hash of the normalized email so the address never reaches the cache.
    The window is short, which bounds how long someone can lock a victim out.
    """

    scope = "login_account"
    default_rate = "10/minute"

    def get_ident_key(self, request) -> str:
        data = getattr(request, "data", None)
        email = data.get("email") if hasattr(data, "get") else None
        if not isinstance(email, str) or not email.strip():
            return super().get_ident_key(request)
        return "account:" + hashlib.sha256(email.strip().lower().encode()).hexdigest()
