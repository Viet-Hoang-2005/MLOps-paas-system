import os
import json
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.pool import QueuePool
from sqlalchemy.dialects.postgresql import JSONB

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(dotenv_path=os.path.join(ROOT_DIR, '.env'))

DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "mlops_paas_db")

DB_HOST_RW = os.environ.get("DB_HOST_RW", "postgres")
DB_HOST_RO = os.environ.get("DB_HOST_RO", "postgres")

AUTOMATIC_DRIFT_OUTBOX_TABLE = "paas_automatic_drift_outbox"

def create_engine_safe(host: str, label: str):
    db_password_encoded = quote_plus(DB_PASSWORD) if DB_PASSWORD else ""
    db_url = f"postgresql://{DB_USER}:{db_password_encoded}@{host}:{DB_PORT}/{DB_NAME}"
    try:
        eng = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        print(f"[{label}] Connected to PostgreSQL at {host}:{DB_PORT}/{DB_NAME}")
        return eng
    except Exception as e:
        print(f"[{label}] Database connection failed: {e}")
        return None
        
engine_rw = create_engine_safe(DB_HOST_RW, "Read Write")
engine_ro = create_engine_safe(DB_HOST_RO, "Read Only")

def init_db():
    if engine_rw is None:
        return
        
    def execute_safe(sql: str, ignore_error: bool = False):
        try:
            with engine_rw.begin() as conn:
                conn.execute(text(sql))
        except Exception as e:
            if not ignore_error:
                print(f"[RW] SQL execution failed: {e}")
            else:
                pass

    # 1. Create table if missing
    execute_safe("""
        CREATE TABLE IF NOT EXISTS paas_production_logs (
            id VARCHAR(255) PRIMARY KEY,
            tenant_id VARCHAR(255),
            project_id VARCHAR(255),
            model_version_id VARCHAR(255),
            model_version VARCHAR(255),
            endpoint_url TEXT,
            request_id VARCHAR(255),
            timestamp TIMESTAMPTZ,
            features JSONB,
            prediction TEXT,
            confidence DOUBLE PRECISION,
            latency_ms DOUBLE PRECISION,
            status_code INTEGER,
            raw_payload JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # 2. Add created_at column if the table was previously created by pandas to_sql
    execute_safe("ALTER TABLE paas_production_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();", ignore_error=True)

    # 3. Migrate text columns to JSONB safely
    execute_safe("ALTER TABLE paas_production_logs ALTER COLUMN features TYPE JSONB USING features::JSONB;", ignore_error=True)
    execute_safe("ALTER TABLE paas_production_logs ALTER COLUMN raw_payload TYPE JSONB USING raw_payload::JSONB;", ignore_error=True)
    execute_safe("ALTER TABLE paas_production_logs ALTER COLUMN prediction TYPE TEXT USING prediction::TEXT;", ignore_error=True)
    execute_safe(
        "ALTER TABLE paas_production_logs ADD COLUMN IF NOT EXISTS project_id VARCHAR(255);"
    )
    execute_safe(
        "ALTER TABLE paas_production_logs ADD COLUMN IF NOT EXISTS model_version_id VARCHAR(255);"
    )

    # 4. Create Indexes
    execute_safe(
        "CREATE INDEX IF NOT EXISTS idx_paas_prod_logs_tenant_model_version "
        "ON paas_production_logs(tenant_id, project_id, model_version_id);"
    )
    execute_safe(
        "CREATE INDEX IF NOT EXISTS idx_paas_prod_logs_model_version "
        "ON paas_production_logs(model_version_id);"
    )
    execute_safe("CREATE INDEX IF NOT EXISTS idx_paas_prod_logs_timestamp ON paas_production_logs(timestamp);")

    # A production-data batch and its automatic-drift notification must become
    # visible together.  Kafka is acknowledged only after this transaction.
    execute_safe(f"""
        CREATE TABLE IF NOT EXISTS {AUTOMATIC_DRIFT_OUTBOX_TABLE} (
            id BIGSERIAL PRIMARY KEY,
            idempotency_key VARCHAR(255) UNIQUE NOT NULL,
            model_version_id VARCHAR(255) NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            locked_until TIMESTAMPTZ,
            published_at TIMESTAMPTZ,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    execute_safe(
        f"CREATE INDEX IF NOT EXISTS idx_paas_auto_drift_outbox_pending "
        f"ON {AUTOMATIC_DRIFT_OUTBOX_TABLE}(published_at, available_at, created_at);"
    )
    
    print("[RW] Initialized 'paas_production_logs' schema.")


def insert_on_conflict_do_nothing(table, conn, keys, data_iter):
    """Pandas ``to_sql`` method that makes Kafka replay safe by event id."""
    rows = [dict(zip(keys, row)) for row in data_iter]
    if not rows:
        return 0

    statement = postgresql_insert(table.table).values(rows)
    if "id" in keys:
        statement = statement.on_conflict_do_nothing(index_elements=["id"])
    result = conn.execute(statement)
    return result.rowcount


def _save_dataframe(conn, df: pd.DataFrame, table_name: str) -> None:
    dtypes = {}
    for col in df.columns:
        if df[col].apply(lambda x: isinstance(x, (dict, list))).any():
            # Let the JSONB dtype serialize dict/list once; json.dumps here would
            # double-encode (JSONB then stores a JSON string instead of an object).
            df[col] = df[col].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
            dtypes[col] = JSONB

    df.to_sql(
        table_name,
        conn,
        if_exists='append',
        index=False,
        chunksize=1000,
        dtype=dtypes,
        method=insert_on_conflict_do_nothing,
    )


def save_dataframe_to_db(df: pd.DataFrame, table_name: str) -> bool:
    if engine_rw is None:
        print("[RW Engine] No database engine available for writing.")
        return False

    try:
        with engine_rw.begin() as conn:
            _save_dataframe(conn, df, table_name)

        record_count = len(df)
        if record_count == 1 and 'id' in df.columns:
            print(f"[RW] Inserted 1 record (ID: {df['id'].iloc[0]}) -> '{table_name}'")
        else:
            print(f"[RW] Inserted {record_count} records -> '{table_name}'")
        return True

    except Exception as e:
        print(f"[RW] Error saving to '{table_name}': {e}")
        return False

def save_dataframe_and_automatic_drift_signals(
    df: pd.DataFrame, table_name: str, signals: list[dict[str, str]]
) -> bool:
    """Persist production data and one idempotent signal per affected model.

    The caller may safely replay a Kafka batch: production events conflict on
    their event id and signals conflict on their deterministic batch key.
    """
    if engine_rw is None:
        print("[RW Engine] No database engine available for writing.")
        return False

    try:
        with engine_rw.begin() as conn:
            _save_dataframe(conn, df, table_name)
            if signals:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO {AUTOMATIC_DRIFT_OUTBOX_TABLE}
                            (idempotency_key, model_version_id)
                        VALUES (:idempotency_key, :model_version_id)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        """
                    ),
                    signals,
                )
        return True
    except Exception as exc:
        print(f"[RW] Error saving production data and automatic drift signals: {exc}")
        return False


def claim_automatic_drift_signals(limit: int, lease_seconds: int) -> list[dict]:
    """Lease pending signals so multiple Consumer replicas do not send the same row."""
    if engine_rw is None:
        return []

    with engine_rw.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                WITH candidates AS (
                    SELECT id
                    FROM {AUTOMATIC_DRIFT_OUTBOX_TABLE}
                    WHERE published_at IS NULL
                      AND available_at <= NOW()
                      AND (locked_until IS NULL OR locked_until < NOW())
                    ORDER BY created_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT :limit
                )
                UPDATE {AUTOMATIC_DRIFT_OUTBOX_TABLE} AS event
                SET attempts = event.attempts + 1,
                    locked_until = NOW() + (:lease_seconds * INTERVAL '1 second')
                FROM candidates
                WHERE event.id = candidates.id
                RETURNING event.id, event.idempotency_key, event.model_version_id, event.attempts
                """
            ),
            {"limit": limit, "lease_seconds": lease_seconds},
        ).mappings()
        return [dict(row) for row in rows]


def mark_automatic_drift_signal_published(event_id: int) -> None:
    if engine_rw is None:
        return
    with engine_rw.begin() as conn:
        conn.execute(
            text(
                f"""
                UPDATE {AUTOMATIC_DRIFT_OUTBOX_TABLE}
                SET published_at = NOW(), locked_until = NULL, last_error = ''
                WHERE id = :event_id AND published_at IS NULL
                """
            ),
            {"event_id": event_id},
        )


def reschedule_automatic_drift_signal(event_id: int, attempts: int, error: str, delay_seconds: int) -> None:
    if engine_rw is None:
        return
    with engine_rw.begin() as conn:
        conn.execute(
            text(
                f"""
                UPDATE {AUTOMATIC_DRIFT_OUTBOX_TABLE}
                SET available_at = NOW() + (:delay_seconds * INTERVAL '1 second'),
                    locked_until = NULL,
                    last_error = :error
                WHERE id = :event_id AND published_at IS NULL AND attempts = :attempts
                """
            ),
            {
                "event_id": event_id,
                "attempts": attempts,
                "delay_seconds": delay_seconds,
                "error": error[:1000],
            },
        )
