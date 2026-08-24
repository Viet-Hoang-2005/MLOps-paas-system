import hashlib
import json

from unittest.mock import Mock
from src import database

class Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *args):
        return False


def test_build_database_url_explicit_and_composed(monkeypatch):
    monkeypatch.setenv("CONTROL_PLANE_DATABASE_URL", "postgresql://explicit")
    assert database.build_control_plane_database_url() == "postgresql://explicit"
    monkeypatch.delenv("CONTROL_PLANE_DATABASE_URL")
    monkeypatch.setenv("DB_USER", "u@x")
    monkeypatch.setenv("DB_PASSWORD", "p word")
    monkeypatch.setenv("DB_HOST_RO", "db")
    assert database.build_control_plane_database_url() == "postgresql://u%40x:p+word@db:5432/mlops_paas_db"
    monkeypatch.delenv("DB_PASSWORD")
    assert database.build_control_plane_database_url() is None


def test_get_model_record_cache_hit(monkeypatch):
    cache = Mock()
    cache.get.return_value = json.dumps({"id": "v"})
    fetch = Mock()
    monkeypatch.setattr(database, "_fetch_model_version_from_db", fetch)
    assert database.get_model_version_record("v", cache) == {"id": "v"}
    fetch.assert_not_called()


def test_get_model_record_cache_miss_and_cache_failure(monkeypatch):
    cache = Mock()
    cache.get.side_effect = RuntimeError("redis")
    cache.setex.side_effect = RuntimeError("redis")
    monkeypatch.setattr(database, "_fetch_model_version_from_db", lambda _: {"id": "v"})
    assert database.get_model_version_record("v", cache) == {"id": "v"}
    cache.setex.assert_called_once()


def test_fetch_model_version_normalizes_values(monkeypatch):
    row = {"id": 1, "project_id": 2, "tenant_id": "t", "version": "v1"}
    mappings = Mock()
    mappings.first.return_value = row
    conn = Mock()
    conn.execute.return_value.mappings.return_value = mappings
    engine = Mock()
    engine.connect.return_value = Context(conn)
    monkeypatch.setattr(database, "model_registry_engine", engine)
    assert database._fetch_model_version_from_db("uuid") == {
        "id": "1", "project_id": "2", "tenant_id": "t", "version": "v1"
    }
    query = str(conn.execute.call_args.args[0])
    assert "version.flavor" in query
    assert "project.model_type" not in query
    mappings.first.return_value = None
    assert database._fetch_model_version_from_db("missing") is None


def test_fetch_requires_database(monkeypatch):
    monkeypatch.setattr(database, "model_registry_engine", None)
    try:
        database._fetch_model_version_from_db("v")
    except RuntimeError as exc:
        assert "unavailable" in str(exc)


def test_verify_api_key_hash_and_project_scope(monkeypatch):
    mappings = Mock()
    mappings.first.return_value = {"tenant_id": "tenant"}
    conn = Mock()
    conn.execute.return_value.mappings.return_value = mappings
    engine = Mock()
    engine.connect.return_value = Context(conn)
    monkeypatch.setattr(database, "model_registry_engine", engine)
    result = database.verify_project_api_key("secret-key", 42)
    assert result == {"tenant_id": "tenant"}
    params = conn.execute.call_args.args[1]
    assert params == {
        "prefix": "secret-key",
        "digest": hashlib.sha256(b"secret-key").hexdigest(),
        "project_pk": 42,
    }
    mappings.first.return_value = None
    assert database.verify_project_api_key("secret-key", 42) is None


def test_verify_api_key_requires_engine_and_value(monkeypatch):
    monkeypatch.setattr(database, "model_registry_engine", None)
    assert database.verify_project_api_key("key", 1) is None
    assert database.verify_project_api_key("", 1) is None
