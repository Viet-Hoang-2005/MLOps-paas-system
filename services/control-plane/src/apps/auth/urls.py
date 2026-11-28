from django.urls import path

from apps.auth.account.api import ProfileEndpoint
from apps.auth.oauth.api import GitHubOAuthEndpoint, GoogleOAuthEndpoint
from apps.auth.passwords.api import (
    PasswordChangeCompleteEndpoint,
    PasswordChangeRequestEndpoint,
    PasswordChangeVerifyEndpoint,
)
from apps.auth.passwords.reset_api import (
    PasswordResetCompleteEndpoint,
    PasswordResetRequestEndpoint,
    PasswordResetVerifyEndpoint,
)
from apps.auth.registration import (
    CompleteRegistrationEndpoint,
    RegistrationOTPRequestEndpoint,
    RegistrationOTPVerifyEndpoint,
)
from apps.auth.sessions.api import JWKSEndpoint, logout_endpoint, refresh_endpoint, token_endpoint

urlpatterns = [
    path("token/", token_endpoint, name="token"),
    path("token/refresh/", refresh_endpoint, name="token-refresh"),
    path("logout/", logout_endpoint, name="logout"),
    path("profile/", ProfileEndpoint.as_view(), name="profile"),
    path("register/request-otp/", RegistrationOTPRequestEndpoint.as_view()),
    path("register/verify-otp/", RegistrationOTPVerifyEndpoint.as_view()),
    path("register/complete/", CompleteRegistrationEndpoint.as_view()),
    path("password-reset/request-otp/", PasswordResetRequestEndpoint.as_view()),
    path("password-reset/verify-otp/", PasswordResetVerifyEndpoint.as_view()),
    path("password-reset/complete/", PasswordResetCompleteEndpoint.as_view()),
    path("oauth/google/", GoogleOAuthEndpoint.as_view()),
    path("oauth/github/", GitHubOAuthEndpoint.as_view()),
    path("password-change/request-otp/", PasswordChangeRequestEndpoint.as_view(), name="password-change-request-otp"),
    path("password-change/verify-otp/", PasswordChangeVerifyEndpoint.as_view(), name="password-change-verify-otp"),
    path("password-change/complete/", PasswordChangeCompleteEndpoint.as_view(), name="password-change-complete"),
    path(".well-known/jwks.json", JWKSEndpoint.as_view(), name="jwks"),
]
