"""Consumer persistence for Django-owned production and outbox tables."""

import os
import re
import time
import uuid
import json
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from src.logging_utils import Summary, get_logger, log_event

logger = get_logger(__name__)
persistence_summary = Summary(logger, "production_persistence_summary")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(dotenv_path=os.path.join(ROOT_DIR, ".env"))

DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "mlops_paas_db")
DB_HOST_RW = os.environ.get("DB_HOST_RW", "postgres")
DB_HOST_RO = os.environ.get("DB_HOST_RO", "postgres")
DB_SCHEMA = os.environ.get("DB_SCHEMA", "control_plane")
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", DB_SCHEMA):
    raise RuntimeError("DB_SCHEMA must be a simple PostgreSQL identifier.")

PREDICTION_TABLE = f'"{DB_SCHEMA}"."production_predictionrecord"'
OUTBOX_TABLE = f'"{DB_SCHEMA}"."observability_eventoutbox"'
VERSION_TABLE = f'"{DB_SCHEMA}"."registry_modelversion"'
PROJECT_TABLE = f'"{DB_SCHEMA}"."catalog_modelproject"'


def create_engine_safe(host: str, label: str):
    password = quote_plus(DB_PASSWORD) if DB_PASSWORD else ""
    url = f"postgresql://{DB_USER}:{password}@{host}:{DB_PORT}/{DB_NAME}"
    try:
        engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        log_event(logger, "INFO", "database_engine_initialized", "Database engine initialized", operation=label)
        return engine
    except Exception as exc:
        log_event(logger, "ERROR", "database_engine_failed", "Database engine initialization failed", operation=label, error_type=type(exc).__name__)
        return None


engine_rw = create_engine_safe(DB_HOST_RW, "Read Write")
engine_ro = create_engine_safe(DB_HOST_RO, "Read Only")


def init_db():
    """Verify migration-owned tables exist. Consumer intentionally performs no DDL."""
    if engine_rw is None:
        raise RuntimeError("Database engine is unavailable.")
    with engine_rw.connect() as conn:
        tables = conn.execute(
            text("SELECT to_regclass(:prediction), to_regclass(:outbox)"),
            {"prediction": f"{DB_SCHEMA}.production_predictionrecord", "outbox": f"{DB_SCHEMA}.observability_eventoutbox"},
        ).one()
    if not all(tables):
        raise RuntimeError("Control Plane migrations have not created production/outbox tables yet.")
    log_event(logger, "INFO", "database_schema_ready", "Migration-owned database schema is ready")


def _records(frame: pd.DataFrame) -> list[dict]:
    records = []
    for row in frame.to_dict("records"):
        if not row.get("public_id") or not row.get("project_id") or not row.get("model_version_id"):
            continue
        records.append({
            "public_id": str(row["public_id"]),
            "project_id": str(row["project_id"]),
            "model_version_id": str(row["model_version_id"]),
            "observed_at": row.get("observed_at"),
            "features": json.dumps(row.get("features") or {}),
            "prediction": str(row.get("prediction") or ""),
            "confidence": row.get("confidence"),
            "latency_ms": row.get("latency_ms"),
            "request_id": str(row.get("request_id") or ""),
        })
    return records


PREDICTION_INSERT = text(
    f"""
    INSERT INTO {PREDICTION_TABLE}
        (public_id, project_id, model_version_id, observed_at, features, prediction, confidence,
         class_mapping, calibration_version, latency_ms, request_id, created_at)
    SELECT CAST(:public_id AS uuid), project.id, version.id, :observed_at, CAST(:features AS jsonb),
           :prediction, :confidence, '{{}}'::jsonb, '', :latency_ms, :request_id, NOW()
    FROM {VERSION_TABLE} version
    INNER JOIN {PROJECT_TABLE} project ON project.id = version.project_id
    WHERE version.public_id = CAST(:model_version_id AS uuid)
      AND project.public_id = CAST(:project_id AS uuid)
    ON CONFLICT (public_id) DO NOTHING
    """
)

OUTBOX_INSERT = text(
    f"""
    INSERT INTO {OUTBOX_TABLE}
        (public_id, idempotency_key, delivery_kind, destination, aggregate_type, aggregate_id,
         event_type, payload, headers, attempts, available_at, last_error, created_at)
    VALUES (CAST(:public_id AS uuid), :idempotency_key, 'webhook', 'automatic_drift',
            'model_version', CAST(:model_version_id AS uuid), 'automatic_drift.requested',
            CAST(:payload AS jsonb), '{{}}'::jsonb, 0, NOW(), '', NOW())
    ON CONFLICT (idempotency_key) DO NOTHING
    """
)


def _signals(signals: list[dict[str, str]]) -> list[dict]:
    return [
        {
            "public_id": str(uuid.uuid4()),
            "idempotency_key": signal["idempotency_key"],
            "model_version_id": signal["model_version_id"],
            "payload": '{"model_version_id": "' + signal["model_version_id"].replace('"', "") + '"}',
        }
        for signal in signals
    ]


def save_prediction_records_and_automatic_drift_signals(predictions: pd.DataFrame, signals: list[dict[str, str]]) -> bool:
    """Write validated prediction rows and webhook outbox rows in one transaction."""
    started = time.perf_counter()
    if engine_rw is None:
        persistence_summary.record(success=False)
        persistence_summary.failure("write", "Database engine unavailable for persistence")
        return False
    try:
        records = _records(predictions)
        with engine_rw.begin() as conn:
            inserted_versions = set()
            if records:
                for record in records:
                    result = conn.execute(PREDICTION_INSERT, record)
                    if result.rowcount:
                        inserted_versions.add(record["model_version_id"])
            outbox_rows = _signals(
                [signal for signal in signals if signal["model_version_id"] in inserted_versions]
            )
            if outbox_rows:
                conn.execute(OUTBOX_INSERT, outbox_rows)
        persistence_summary.record(duration_ms=(time.perf_counter() - started) * 1000, records=len(records), production_samples=len(records), batches=1)
        persistence_summary.recovery("write")
        return True
    except Exception as exc:
        persistence_summary.record(success=False, duration_ms=(time.perf_counter() - started) * 1000)
        persistence_summary.failure("write", "Prediction and automatic-drift transaction failed", error_type=type(exc).__name__)
        return False


def claim_automatic_drift_signals(limit: int, lease_seconds: int) -> list[dict]:
    """Lease only webhook/automatic-drift events; Kafka workers cannot claim them."""
    if engine_rw is None:
        return []
    with engine_rw.begin() as conn:
        rows = conn.execute(text(f"""
            WITH candidates AS (
                SELECT id FROM {OUTBOX_TABLE}
                WHERE delivery_kind = 'webhook' AND destination = 'automatic_drift'
                  AND published_at IS NULL AND available_at <= NOW()
                  AND (locked_until IS NULL OR locked_until <= NOW())
                ORDER BY available_at, created_at, id FOR UPDATE SKIP LOCKED LIMIT :limit
            )
            UPDATE {OUTBOX_TABLE} event SET attempts = event.attempts + 1,
                locked_until = NOW() + (:lease_seconds * INTERVAL '1 second')
            FROM candidates WHERE event.id = candidates.id
            RETURNING event.id, event.idempotency_key, event.payload, event.attempts
        """), {"limit": limit, "lease_seconds": lease_seconds}).mappings()
        return [dict(row) | {"model_version_id": dict(row)["payload"]["model_version_id"]} for row in rows]


def mark_automatic_drift_signal_published(event_id: int) -> None:
    if engine_rw is None:
        return
    with engine_rw.begin() as conn:
        conn.execute(text(f"UPDATE {OUTBOX_TABLE} SET published_at = NOW(), locked_until = NULL, last_error = '' WHERE id = :event_id AND published_at IS NULL"), {"event_id": event_id})


def reschedule_automatic_drift_signal(event_id: int, attempts: int, error: str, delay_seconds: int) -> None:
    if engine_rw is None:
        return
    with engine_rw.begin() as conn:
        conn.execute(text(f"""
            UPDATE {OUTBOX_TABLE} SET available_at = NOW() + (:delay_seconds * INTERVAL '1 second'),
                locked_until = NULL, last_error = :error
            WHERE id = :event_id AND published_at IS NULL AND attempts = :attempts
        """), {"event_id": event_id, "attempts": attempts, "delay_seconds": delay_seconds, "error": error[:1000]})
