import pandas as pd
from unittest.mock import Mock

from src import database


class Context:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


def test_create_engine_safe_quotes_password(monkeypatch):
    monkeypatch.setattr(database, "DB_USER", "user")
    monkeypatch.setattr(database, "DB_PASSWORD", "p@ss word")
    create = Mock(return_value="engine")
    monkeypatch.setattr(database, "create_engine", create)
    assert database.create_engine_safe("db", "RW") == "engine"
    assert "p%40ss+word" in create.call_args.args[0]


def test_init_db_only_checks_migration_owned_tables(monkeypatch):
    connection = Mock()
    connection.execute.return_value.rowcount = 1
    connection.execute.return_value.one.return_value = ("production_predictionrecord", "eventoutbox")
    engine = Mock()
    engine.connect.return_value = Context(connection)
    monkeypatch.setattr(database, "engine_rw", engine)

    database.init_db()

    statement = str(connection.execute.call_args.args[0])
    assert "to_regclass" in statement
    assert "CREATE TABLE" not in statement


def test_init_db_rejects_unmigrated_schema(monkeypatch):
    connection = Mock()
    connection.execute.return_value.one.return_value = (None, None)
    engine = Mock()
    engine.connect.return_value = Context(connection)
    monkeypatch.setattr(database, "engine_rw", engine)

    try:
        database.init_db()
    except RuntimeError as exc:
        assert "migrations" in str(exc)
    else:
        raise AssertionError("Expected schema readiness failure")


def test_prediction_and_webhook_outbox_share_transaction(monkeypatch):
    connection = Mock()
    connection.execute.return_value.rowcount = 1
    engine = Mock()
    engine.begin.return_value = Context(connection)
    monkeypatch.setattr(database, "engine_rw", engine)

    frame = pd.DataFrame([{
        "public_id": "00000000-0000-0000-0000-000000000001",
        "project_id": "00000000-0000-0000-0000-000000000002",
        "model_version_id": "00000000-0000-0000-0000-000000000003",
        "observed_at": "2026-01-01T00:00:00Z", "features": {"x": 1},
        "prediction": "safe", "confidence": 80.0, "latency_ms": 1.0, "request_id": "request-1",
    }])
    signals = [{"model_version_id": "00000000-0000-0000-0000-000000000003", "idempotency_key": "signal-1"}]

    assert database.save_prediction_records_and_automatic_drift_signals(frame, signals)
    assert connection.execute.call_count == 2
    prediction_sql = str(connection.execute.call_args_list[0].args[0])
    assert "INNER JOIN" in prediction_sql and "ON CONFLICT (public_id) DO NOTHING" in prediction_sql
    outbox_sql = str(connection.execute.call_args_list[1].args[0])
    assert "'webhook'" in outbox_sql and "'automatic_drift'" in outbox_sql


def test_webhook_claim_uses_kind_destination_and_skip_locked(monkeypatch):
    result = Mock()
    result.mappings.return_value = []
    connection = Mock()
    connection.execute.return_value = result
    engine = Mock()
    engine.begin.return_value = Context(connection)
    monkeypatch.setattr(database, "engine_rw", engine)

    assert database.claim_automatic_drift_signals(25, 90) == []
    statement = str(connection.execute.call_args.args[0])
    assert "delivery_kind = 'webhook'" in statement
    assert "destination = 'automatic_drift'" in statement
    assert "FOR UPDATE SKIP LOCKED" in statement
