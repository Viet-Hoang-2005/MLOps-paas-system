import pandas as pd

from unittest.mock import Mock
from src import database

class Context:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *args):
        return False


def test_create_engine_safe_quotes_password(monkeypatch):
    monkeypatch.setattr(database, "DB_USER", "user")
    monkeypatch.setattr(database, "DB_PASSWORD", "p@ss word")
    create = Mock(return_value="engine")
    monkeypatch.setattr(database, "create_engine", create)
    assert database.create_engine_safe("db", "RW") == "engine"
    assert "p%40ss+word" in create.call_args.args[0]


def test_create_engine_safe_failure_returns_none(monkeypatch):
    monkeypatch.setattr(database, "create_engine", Mock(side_effect=RuntimeError("bad")))
    assert database.create_engine_safe("db", "RW") is None


def test_save_dataframe_handles_no_engine(monkeypatch):
    monkeypatch.setattr(database, "engine_rw", None)
    assert not database.save_dataframe_to_db(pd.DataFrame({"id": ["1"]}), "logs")


def test_save_dataframe_marks_nested_columns_jsonb(monkeypatch):
    connection = Mock()
    engine = Mock()
    engine.begin.return_value = Context(connection)
    monkeypatch.setattr(database, "engine_rw", engine)
    df = pd.DataFrame({"id": ["1"], "features": [{"x": 1}], "prediction": ["ok"]})
    to_sql = Mock()
    monkeypatch.setattr(pd.DataFrame, "to_sql", to_sql)
    assert database.save_dataframe_to_db(df, "logs")
    assert to_sql.call_args.kwargs["dtype"]["features"] is database.JSONB
    assert to_sql.call_args.kwargs["method"] is database.insert_on_conflict_do_nothing
    assert df.loc[0, "features"] == {"x": 1}


def test_save_dataframe_exception_returns_false(monkeypatch):
    monkeypatch.setattr(database, "engine_rw", Mock())
    monkeypatch.setattr(pd.DataFrame, "to_sql", Mock(side_effect=RuntimeError("db")))
    assert not database.save_dataframe_to_db(pd.DataFrame({"id": ["1"]}), "logs")


def test_insert_on_conflict_do_nothing_uses_event_id(monkeypatch):
    statement = Mock()
    statement.values.return_value = statement
    statement.on_conflict_do_nothing.return_value = statement
    insert = Mock(return_value=statement)
    monkeypatch.setattr(database, "postgresql_insert", insert)
    result = Mock(rowcount=2)
    connection = Mock()
    connection.execute.return_value = result
    table = type("PandasTable", (), {"table": "paas_production_logs"})()

    assert database.insert_on_conflict_do_nothing(
        table, connection, ["id", "prediction"], [("event-1", "ok"), ("event-2", "bad")]
    ) == 2
    statement.on_conflict_do_nothing.assert_called_once_with(index_elements=["id"])


def test_save_dataframe_and_signals_share_one_transaction(monkeypatch):
    connection = Mock()
    engine = Mock()
    engine.begin.return_value = Context(connection)
    monkeypatch.setattr(database, "engine_rw", engine)
    save = Mock()
    monkeypatch.setattr(database, "_save_dataframe", save)

    assert database.save_dataframe_and_automatic_drift_signals(
        pd.DataFrame({"id": ["event-1"]}),
        "paas_production_logs",
        [{"model_version_id": "version-1", "idempotency_key": "signal-1"}],
    )

    save.assert_called_once()
    assert connection.execute.call_args.args[1] == [
        {"model_version_id": "version-1", "idempotency_key": "signal-1"}
    ]


def test_save_dataframe_and_signals_handles_no_engine(monkeypatch):
    monkeypatch.setattr(database, "engine_ro", None)
    monkeypatch.setattr(database, "engine_rw", None)
    assert not database.save_dataframe_and_automatic_drift_signals(
        pd.DataFrame({"id": ["event-1"]}), "paas_production_logs", []
    )


def test_reschedule_signal_uses_claim_attempt_count(monkeypatch):
    connection = Mock()
    engine = Mock()
    engine.begin.return_value = Context(connection)
    monkeypatch.setattr(database, "engine_rw", engine)

    database.reschedule_automatic_drift_signal(4, 3, "HTTP 503", 20)

    assert connection.execute.call_args.args[1] == {
        "event_id": 4,
        "attempts": 3,
        "delay_seconds": 20,
        "error": "HTTP 503",
    }


def test_claim_signal_uses_skip_locked_and_expiring_lease(monkeypatch):
    result = Mock()
    result.mappings.return_value = []
    connection = Mock()
    connection.execute.return_value = result
    engine = Mock()
    engine.begin.return_value = Context(connection)
    monkeypatch.setattr(database, "engine_rw", engine)

    assert database.claim_automatic_drift_signals(25, 90) == []

    statement = str(connection.execute.call_args.args[0])
    assert "FOR UPDATE SKIP LOCKED" in statement
    assert "locked_until = NOW() + (:lease_seconds * INTERVAL '1 second')" in statement
    assert connection.execute.call_args.args[1] == {"limit": 25, "lease_seconds": 90}


def test_init_db_creates_model_version_count_index(monkeypatch):
    connection = Mock()
    engine = Mock()
    engine.begin.return_value = Context(connection)
    monkeypatch.setattr(database, "engine_rw", engine)

    database.init_db()

    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert any("idx_paas_prod_logs_model_version" in statement for statement in statements)
