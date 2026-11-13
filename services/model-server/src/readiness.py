"""Bounded dependency probes; never return connection strings or credentials."""

from sqlalchemy import text


def dependency_checks(engine, redis_factory, producer):
    checks = {}
    try:
        if engine is None:
            raise RuntimeError("Database unavailable")
        with engine.connect() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))
            connection.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unavailable"
    client = None
    try:
        client = redis_factory()
        checks["redis"] = "ok" if client.ping() else "unavailable"
    except Exception:
        checks["redis"] = "unavailable"
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                checks["redis"] = "unavailable"
    try:
        metadata = producer.list_topics(timeout=2)
        checks["kafka"] = "ok" if metadata.brokers else "unavailable"
    except Exception:
        checks["kafka"] = "unavailable"
    return checks
