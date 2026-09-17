"""Authentication decisions independent from the FastAPI route module."""

import json
import uuid

from fastapi import HTTPException


async def fetch_public_key(
    kid,
    *,
    cache,
    jwks_url,
    summary,
    http_client_factory,
    rsa_algorithm,
):
    if kid not in cache:
        try:
            async with http_client_factory() as client:
                response = await client.get(jwks_url, timeout=5.0)
                response.raise_for_status()
                for key_data in response.json().get("keys", []):
                    if key_data.get("kid") == kid:
                        public_key = rsa_algorithm.from_jwk(json.dumps(key_data))
                        cache[kid] = public_key
                        summary.recovery("fetch")
                        return public_key
        except Exception as exc:
            summary.failure(
                "fetch",
                "JWKS fetch or parse failed",
                error_type=type(exc).__name__,
            )
            return None
    return cache.get(kid)


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
        model_record = get_model_version_record(
            version_id,
            redis_client=redis_client,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
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
        key_record = verify_project_api_key(api_key, model_record["project_pk"])
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
    except jwt_module.InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Unauthorized: Invalid token ({exc})",
        )
