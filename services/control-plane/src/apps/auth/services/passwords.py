from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.response import Response

from apps.auth.models import CustomUser
from apps.auth.services.cookies import clear_refresh_token_cookie
from apps.auth.services.otp import read_token
from apps.auth.services.tokens import create_auth_response, revoke_user_refresh_tokens


@transaction.atomic
def complete_password_update(token, password, *, actor=None):
    purpose = "password_reset" if actor is None else "password_change"
    payload = read_token(token, purpose, consume=False)
    email = payload["email"].strip().lower()
    accounts = CustomUser.objects.select_for_update().filter(email__iexact=email, is_active=True)
    if actor is not None:
        accounts = accounts.filter(pk=actor.pk)
    # Preserve the existing recovery rule for legacy duplicate email casing.
    user = accounts.order_by("-date_joined").first()
    if user is None:
        raise ValidationError({"token": "User account not found or inactive."})
    if actor is not None and actor.session_version != user.session_version:
        raise AuthenticationFailed("This session is no longer valid.", code="session_revoked")
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise ValidationError({"new_password": list(exc.messages)}) from exc

    user.set_password(password)
    user.session_version += 1
    user.save(update_fields=["password", "session_version"])
    revoke_user_refresh_tokens(user)
    if actor is not None:
        response = create_auth_response(user, {"message": "Password changed."})
    else:
        response = Response({"message": "Password reset completed."})
        clear_refresh_token_cookie(response)
    # Keep the verification token available if password or session persistence fails.
    read_token(token, purpose, consume=True)
    return response
