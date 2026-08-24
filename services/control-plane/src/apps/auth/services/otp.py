import secrets

from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from rest_framework.exceptions import ValidationError

OTP_TTL_SECONDS = 600
TOKEN_TTL_SECONDS = 900


def send_otp(*, email, purpose):
    code = f"{secrets.randbelow(1_000_000):06d}"
    cache.set(_cache_key(email, purpose), code, OTP_TTL_SECONDS)
    send_mail(
        subject=f"MLOps PaaS {purpose.replace('_', ' ')} code",
        message=f"Your verification code is {code}. It expires in 10 minutes.",
        from_email=None,
        recipient_list=[email],
        fail_silently=False,
    )


def verify_otp(*, email, code, purpose):
    key = _cache_key(email, purpose)
    expected = cache.get(key)
    if not expected or not secrets.compare_digest(str(expected), str(code)):
        raise ValidationError({"otp_code": "Invalid or expired verification code."})
    cache.delete(key)
    return signing.dumps({"email": email, "purpose": purpose}, salt="identity-otp")


def read_token(token, purpose):
    try:
        payload = signing.loads(
            token,
            salt="identity-otp",
            max_age=TOKEN_TTL_SECONDS,
        )
    except signing.BadSignature as exc:
        raise ValidationError({"token": "Invalid or expired verification token."}) from exc
    if payload.get("purpose") != purpose:
        raise ValidationError({"token": "Verification token has the wrong purpose."})
    return payload


def _cache_key(email, purpose):
    return f"identity:otp:{purpose}:{email.strip().lower()}"
