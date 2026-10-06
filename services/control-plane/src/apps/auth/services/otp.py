import secrets
import time

from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from rest_framework.exceptions import Throttled, ValidationError

OTP_TTL_SECONDS = 600
TOKEN_TTL_SECONDS = 900
OTP_COOLDOWN_SECONDS = 60
MAX_OTP_ATTEMPTS = 5
MAX_OTP_REQUESTS_PER_HOUR = 5


def _cache_key(email: str, purpose: str) -> str:
    return f"identity:otp:{purpose}:{email.strip().lower()}"


def _attempts_key(email: str, purpose: str) -> str:
    return f"identity:otp:attempts:{purpose}:{email.strip().lower()}"


def _cooldown_key(email: str, purpose: str) -> str:
    return f"identity:otp:cooldown:{purpose}:{email.strip().lower()}"


def _hourly_key(email: str, purpose: str) -> str:
    return f"identity:otp:hourly:{purpose}:{email.strip().lower()}"


def check_and_record_otp_cooldown(*, email: str, purpose: str) -> None:
    """
    Guards against email spam and resource exhaustion by enforcing:
    1. A 60-second cooldown between code requests for the same email & purpose.
    2. A maximum cap of 5 code requests per hour.
    """
    clean_email = email.strip().lower()
    cooldown_key = _cooldown_key(clean_email, purpose)
    last_sent_at = cache.get(cooldown_key)
    if last_sent_at is not None:
        elapsed = int(time.time() - float(last_sent_at))
        remaining = max(1, OTP_COOLDOWN_SECONDS - elapsed)
        raise Throttled(
            wait=remaining,
            detail=f"Please wait {remaining} seconds before requesting another verification code.",
        )

    hourly_key = _hourly_key(clean_email, purpose)
    hourly_count = cache.get(hourly_key) or 0
    if hourly_count >= MAX_OTP_REQUESTS_PER_HOUR:
        raise Throttled(
            wait=3600,
            detail="Too many verification codes requested for this email. Please try again later.",
        )

    cache.set(cooldown_key, time.time(), OTP_COOLDOWN_SECONDS)
    cache.set(hourly_key, hourly_count + 1, 3600)


def send_otp(*, email: str, purpose: str) -> None:
    check_and_record_otp_cooldown(email=email, purpose=purpose)
    code = f"{secrets.randbelow(1_000_000):06d}"
    key = _cache_key(email, purpose)
    attempts_key = _attempts_key(email, purpose)

    cache.set(key, code, OTP_TTL_SECONDS)
    cache.delete(attempts_key)

    send_mail(
        subject=f"MLOps PaaS {purpose.replace('_', ' ')} code",
        message=f"Your verification code is {code}. It expires in 10 minutes.",
        from_email=None,
        recipient_list=[email.strip()],
        fail_silently=False,
    )


def verify_otp(*, email: str, code: str, purpose: str) -> str:
    clean_email = email.strip().lower()
    key = _cache_key(clean_email, purpose)
    attempts_key = _attempts_key(clean_email, purpose)

    attempts = cache.get(attempts_key) or 0
    if attempts >= MAX_OTP_ATTEMPTS:
        cache.delete(key)
        raise ValidationError({
            "otp_code": "Too many failed attempts. This verification code is no longer valid. Please request a new code."
        })

    expected = cache.get(key)
    if not expected:
        raise ValidationError({"otp_code": "Invalid or expired verification code."})

    if not secrets.compare_digest(str(expected), str(code).strip()):
        attempts += 1
        cache.set(attempts_key, attempts, OTP_TTL_SECONDS)
        if attempts >= MAX_OTP_ATTEMPTS:
            cache.delete(key)
            cache.delete(attempts_key)
            raise ValidationError({
                "otp_code": "Too many failed attempts. This verification code is no longer valid. Please request a new code."
            })
        remaining = MAX_OTP_ATTEMPTS - attempts
        raise ValidationError({
            "otp_code": f"Invalid verification code. You have {remaining} attempt{'s' if remaining > 1 else ''} remaining."
        })

    # Successful verification: delete code and attempt counter immediately
    cache.delete(key)
    cache.delete(attempts_key)
    jti = secrets.token_hex(16)
    return signing.dumps(
        {"email": clean_email, "purpose": purpose, "jti": jti},
        salt="identity-otp",
    )


def read_token(token: str, purpose: str, consume: bool = True) -> dict:
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

    jti = payload.get("jti")
    if not jti:
        raise ValidationError({"token": "Invalid verification token format."})

    consumed_key = f"identity:token:consumed:{jti}"
    if consume:
        was_added = cache.add(consumed_key, True, TOKEN_TTL_SECONDS)
        if not was_added:
            raise ValidationError({"token": "Verification token has already been used."})
    else:
        if cache.get(consumed_key):
            raise ValidationError({"token": "Verification token has already been used."})

    return payload
