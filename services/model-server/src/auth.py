"""Authentication decisions independent from the FastAPI route module."""

import asyncio
import contextlib
import json
import logging
import time
import uuid

from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _cached_key(cache, kid):
    """Return (found, key): found is True for a cached key or a cached miss."""
    if hasattr(cache, "is_negative") and cache.is_negative(kid):
        return True, None
    cached = cache.get(kid) if hasattr(cache, "get") else None
    return cached is not None, cached


async def fetch_public_key(
    kid,
    *,
    cache,
    jwks_url,
    summary,
    http_client_factory,
    rsa_algorithm,
):
    found, key = _cached_key(cache, kid)
    if found:
        return key

    # One download at a time: concurrent requests for an unknown kid wait for the
    # in-flight fetch and then read its result from the cache.
    async with getattr(cache, "fetch_lock", None) or contextlib.nullcontext():
        found, key = _cached_key(cache, kid)
        if found:
            return key
        last_fetch_at = getattr(cache, "last_fetch_at", None)
        interval = getattr(cache, "min_refetch_interval", 0)
        if last_fetch_at is not None and time.monotonic() - last_fetch_at < interval:
            # The key set was loaded moments ago. Do not hit the Control Plane again
            # for another kid, and do not cache a miss: a rotated key may appear soon.
            return None
        if hasattr(cache, "last_fetch_at"):
            cache.last_fetch_at = time.monotonic()
        return await _download_public_key(
            kid,
            cache=cache,
            jwks_url=jwks_url,
            summary=summary,
            http_client_factory=http_client_factory,
            rsa_algorithm=rsa_algorithm,
        )


async def _download_public_key(
    kid,
    *,
    cache,
    jwks_url,
    summary,
    http_client_factory,
    rsa_algorithm,
):
    try:
        async with http_client_factory() as client:
            response = await client.get(jwks_url, timeout=5.0)
            response.raise_for_status()
            keys_data = response.json().get("keys", [])
            kid_found_in_payload = False
            found_key = None
            for key_data in keys_data:
                k_id = key_data.get("kid")
                if not k_id:
                    continue
                if k_id == kid:
                    kid_found_in_payload = True
                    pub_key = rsa_algorithm.from_jwk(json.dumps(key_data))
                    cache[k_id] = pub_key
                    found_key = pub_key
                else:
                    try:
                        pub_key = rsa_algorithm.from_jwk(json.dumps(key_data))
                        cache[k_id] = pub_key
                    except Exception:
                        pass

            if found_key is not None:
                summary.recovery("fetch")
                return found_key

            if not kid_found_in_payload:
                if hasattr(cache, "set_negative"):
                    cache.set_negative(kid)
            return None
    except Exception as exc:
        summary.failure(
            "fetch",
            "JWKS fetch or parse failed",
            error_type=type(exc).__name__,
        )
        return None


async def authorize_model_access(
    version_id,
    api_key,
    authorization,
    *,
    redis_client,
    get_model_version_record,
    verify_project_api_key,
    get_public_key,
    jwt_module,
):
    try:
        uuid.UUID(version_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Model version not found.") from None
    try:
        # Redis and PostgreSQL clients block; run them in a worker thread, not on the event loop.
        model_record = await asyncio.to_thread(
            get_model_version_record,
            version_id,
            redis_client=redis_client,
        )
    except Exception as exc:
        logger.error("Model registry lookup failed (%s).", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Model registry is temporarily unavailable.") from None
    if not model_record:
        raise HTTPException(status_code=404, detail="Model version not found.")
    model_tenant_id = model_record["tenant_id"]
    if model_record["access_mode"] == "public":
        return {
            "tenant_id": model_tenant_id,
            "auth_type": "public",
            "model_record": model_record,
        }
    if api_key:
        key_record = await asyncio.to_thread(verify_project_api_key, api_key, model_record["project_pk"])
        if not key_record:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: Invalid or revoked API Key",
            )
        if key_record["tenant_id"] != model_tenant_id:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: You do not have permission to access this model.",
            )
        return {
            "tenant_id": key_record["tenant_id"],
            "auth_type": "api_key",
            "model_record": model_record,
        }
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Missing API Key or Bearer Token",
        )
    token = authorization.split(" ")[1]
    try:
        unverified_header = jwt_module.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: JWT missing 'kid' header",
            )
        public_key = await get_public_key(kid)
        if not public_key:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: Unable to verify token signature",
            )
        payload = jwt_module.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="mlops-paas",
        )
        if payload.get("tenant_id") != model_tenant_id:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: You do not have permission to access this model.",
            )
        payload["auth_type"] = "jwt"
        payload["model_record"] = model_record
        return payload
    except jwt_module.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Unauthorized: Token has expired")
    except jwt_module.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid token")
