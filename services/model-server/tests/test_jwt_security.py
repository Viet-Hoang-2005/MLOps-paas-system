"""Verify the inference token contract using ephemeral RSA keys and real JWTs."""

import time
from unittest.mock import AsyncMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from src.auth import authorize_model_access

VERSION_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def access_claims():
    now = int(time.time())
    return {
        "tenant_id": "tenant", "user_id": 1, "token_type": "access", "jti": "test-id",
        "iss": "django-control-plane", "aud": "mlops-paas", "iat": now, "exp": now + 60,
    }


async def authorize(claims, signing_key, *, access_mode="private", verification_key=None):
    token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test-key"})
    return await authorize_model_access(
        VERSION_ID, None, f"Bearer {token}", redis_client=None,
        get_model_version_record=lambda *a, **kw: {"tenant_id": "tenant", "access_mode": access_mode},
        verify_project_api_key=None,
        get_public_key=AsyncMock(return_value=verification_key or signing_key.public_key()),
        jwt_module=jwt,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("access_mode", ["private", "protected"])
@pytest.mark.parametrize("token_type", ["access", "refresh", "sliding", "", None])
async def test_gateway_requires_access_token(signing_key, token_type, access_mode):
    claims = access_claims()
    claims["token_type"] = token_type
    if token_type == "access":
        assert (await authorize(claims, signing_key, access_mode=access_mode))["auth_type"] == "jwt"
    else:
        # Refresh tokens are rejected regardless of their Control Plane blacklist state.
        with pytest.raises(HTTPException) as exc:
            await authorize(claims, signing_key, access_mode=access_mode)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("claim", ["exp", "iat", "jti", "user_id", "tenant_id", "token_type", "iss", "aud"])
async def test_gateway_rejects_missing_required_claim(signing_key, claim):
    claims = access_claims()
    del claims[claim]
    with pytest.raises(HTTPException) as exc:
        await authorize(claims, signing_key)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["expired", "issuer", "audience", "signature", "tenant"])
async def test_gateway_rejects_invalid_access_token(signing_key, variant):
    claims = access_claims()
    verification_key = None
    if variant == "expired":
        claims["exp"] = int(time.time()) - 60
    elif variant == "issuer":
        claims["iss"] = "another-service"
    elif variant == "audience":
        claims["aud"] = "another-service"
    elif variant == "tenant":
        claims["tenant_id"] = "another-tenant"
    else:
        verification_key = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    with pytest.raises(HTTPException) as exc:
        await authorize(claims, signing_key, verification_key=verification_key)
    assert exc.value.status_code == (403 if variant == "tenant" else 401)
