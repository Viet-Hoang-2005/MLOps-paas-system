from django.urls import path

from .account_endpoints import (
    AccountDeleteEndpoint,
    AvatarHistoryEndpoint,
    AvatarSelectEndpoint,
    PasswordChangeCompleteEndpoint,
    PasswordChangeRequestEndpoint,
    PasswordChangeVerifyEndpoint,
    ProfileEndpoint,
)
from .endpoints import JWKSEndpoint, RegisterEndpoint, refresh_endpoint, token_endpoint
from .oauth_endpoints import GitHubOAuthEndpoint, GoogleOAuthEndpoint
from .registration_endpoints import (
    CompleteRegistrationEndpoint,
    PasswordResetCompleteEndpoint,
    PasswordResetRequestEndpoint,
    PasswordResetVerifyEndpoint,
    RegistrationOTPRequestEndpoint,
    RegistrationOTPVerifyEndpoint,
)

urlpatterns = [
    path("token/", token_endpoint, name="token"),
    path("token/refresh/", refresh_endpoint, name="token-refresh"),
    path("register/", RegisterEndpoint.as_view(), name="register"),
    path("profile/", ProfileEndpoint.as_view(), name="profile"),
    path("register/request-otp/", RegistrationOTPRequestEndpoint.as_view()),
    path("register/verify-otp/", RegistrationOTPVerifyEndpoint.as_view()),
    path("register/complete/", CompleteRegistrationEndpoint.as_view()),
    path("password-reset/request-otp/", PasswordResetRequestEndpoint.as_view()),
    path("password-reset/verify-otp/", PasswordResetVerifyEndpoint.as_view()),
    path("password-reset/complete/", PasswordResetCompleteEndpoint.as_view()),
    path("oauth/google/", GoogleOAuthEndpoint.as_view()),
    path("oauth/github/", GitHubOAuthEndpoint.as_view()),
    path("profile/avatars/", AvatarHistoryEndpoint.as_view()),
    path("profile/avatars/<uuid:avatar_id>/select/", AvatarSelectEndpoint.as_view()),
    path("profile/delete/", AccountDeleteEndpoint.as_view()),
    path("profile/password-otp/", PasswordChangeRequestEndpoint.as_view()),
    path("profile/password-otp/verify/", PasswordChangeVerifyEndpoint.as_view()),
    path("profile/change-password/", PasswordChangeCompleteEndpoint.as_view()),
    path(".well-known/jwks.json", JWKSEndpoint.as_view(), name="jwks"),
]
