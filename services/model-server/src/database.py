import hashlib
import json
import os
import re
from typing import Any, Dict
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from src.logging_utils import Summary, get_logger

cache_summary = Summary(get_logger(__name__), "registry_cache_summary")

MODEL_RECORD_CACHE_TTL = int(os.environ.get("MODEL_RECORD_CACHE_TTL_SECONDS", "30"))


def build_control_plane_database_url():
    explicit_url = os.environ.get("CONTROL_PLANE_DATABASE_URL")
    if explicit_url:
        return explicit_url
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    if not db_user or not db_password:
        return None
    return (
        f"postgresql://{quote_plus(db_user)}:{quote_plus(db_password)}"
        f"@{os.environ.get('DB_HOST_RO', 'postgres')}:{os.environ.get('DB_PORT', '5432')}"
        f"/{os.environ.get('DB_NAME', 'mlops_paas_db')}"
    )


CONTROL_PLANE_DATABASE_URL = build_control_plane_database_url()
CONTROL_PLANE_DB_SCHEMA = os.environ.get("CONTROL_PLANE_DB_SCHEMA") or os.environ.get("DB_SCHEMA", "control_plane")
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", CONTROL_PLANE_DB_SCHEMA):
    raise RuntimeError("CONTROL_PLANE_DB_SCHEMA must be a simple PostgreSQL identifier.")

model_registry_engine = (
    create_engine(
        CONTROL_PLANE_DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"options": f"-c search_path={CONTROL_PLANE_DB_SCHEMA},public"},
    )
    if CONTROL_PLANE_DATABASE_URL
    else None
)


def _fetch_model_version_from_db(version_id: str) -> Dict[str, Any] | None:
    if model_registry_engine is None:
        raise RuntimeError("Model registry database is unavailable.")
    query = text("""
        SELECT
            version.public_id AS id,
            version.version,
            version.flavor,
            version.stage,
            project.id AS project_pk,
            project.public_id AS project_id,
            project.name,
            project.access_mode,
            users.tenant_id,
            endpoint.runtime_name AS endpoint_container_name,
            endpoint.internal_url,
            endpoint.public_url,
            endpoint.health_status,
            deployment.status AS deployment_status
        FROM registry_modelversion AS version
        INNER JOIN catalog_modelproject AS project ON project.id = version.project_id
        INNER JOIN identity_customuser AS users ON users.id = project.owner_id
        LEFT JOIN LATERAL (
            SELECT d.* FROM deployment_deployment AS d
            WHERE d.version_id = version.id AND d.status IN ('healthy', 'deploying')
            ORDER BY d.created_at DESC LIMIT 1
        ) AS deployment ON TRUE
        LEFT JOIN deployment_endpoint AS endpoint ON endpoint.deployment_id = deployment.id
        WHERE version.public_id = :version_id AND project.is_active = TRUE
        LIMIT 1
    """)
    with model_registry_engine.connect() as connection:
        row = connection.execute(query, {"version_id": version_id}).mappings().first()
    if not row:
        return None
    return {key: value.isoformat() if hasattr(value, "isoformat") else str(value) if key in {"id", "project_id"} else value for key, value in dict(row).items()}


def get_model_version_record(version_id: str, redis_client=None):
    cache_key = f"model-version:{version_id}"
    if redis_client is not None:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
    record = _fetch_model_version_from_db(version_id)
    if record and redis_client is not None:
        try:
            redis_client.setex(cache_key, MODEL_RECORD_CACHE_TTL, json.dumps(record))
        except Exception:
            pass
    return record


def invalidate_model_version_cache(version_id: str, redis_client=None) -> bool:
    """Invalidate the cached model version record in Redis."""
    if redis_client is None or not version_id:
        return False
    try:
        cache_key = f"model-version:{version_id}"
        deleted = redis_client.delete(cache_key)
        cache_summary.recovery("invalidate")
        return bool(deleted)
    except Exception as exc:
        cache_summary.failure("invalidate", "Model registry cache invalidation failed", error_type=type(exc).__name__)
        return False


def verify_project_api_key(raw_key: str, project_pk: int):
    if model_registry_engine is None or not raw_key:
        return None
    query = text("""
        SELECT users.tenant_id
        FROM access_control_userapikey AS api_key
        INNER JOIN identity_customuser AS users ON users.id = api_key.user_id
        INNER JOIN access_control_userapikey_allowed_projects AS allowed
            ON allowed.userapikey_id = api_key.id
        WHERE api_key.key_prefix = :prefix
          AND api_key.key_hash = :digest
          AND api_key.revoked_at IS NULL
          AND allowed.modelproject_id = :project_pk
        LIMIT 1
    """)
    with model_registry_engine.connect() as connection:
        row = connection.execute(
            query,
            {
                "prefix": raw_key[:16],
                "digest": hashlib.sha256(raw_key.encode()).hexdigest(),
                "project_pk": project_pk,
            },
        ).mappings().first()
    return dict(row) if row else None
