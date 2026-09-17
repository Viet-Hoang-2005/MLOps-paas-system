from unittest.mock import Mock

from src import kafka_runtime as main
from src.batching import PREDICTION_RECORD_COLUMNS
from src.models import KafkaRecord


class FakeConsumer:
    def __init__(self):
        self.commits = []

    def commit(self, offsets, asynchronous):
        self.commits.append((offsets, asynchronous))
        return []


def record(payload=None, offset=0, partition=0):
    return KafkaRecord(
        payload or {
            "id": "00000000-0000-0000-0000-000000000001",
            "project_id": "00000000-0000-0000-0000-000000000002",
            "model_version_id": "00000000-0000-0000-0000-000000000003",
            "timestamp": "2026-01-01T00:00:00Z", "features": {"x": 1},
            "prediction": "safe", "confidence": 80.0, "status_code": 200,
        },
        topic="events", partition=partition, offset=offset,
    )


def test_prediction_batch_keeps_only_owned_schema_fields():
    frame = main.build_prediction_records_dataframe([record()])
    assert list(frame) == list(PREDICTION_RECORD_COLUMNS)
    assert frame.loc[0, "public_id"] == "00000000-0000-0000-0000-000000000001"
    assert "tenant_id" not in frame and "status_code" not in frame


def test_prediction_batch_excludes_failed_or_featureless_events():
    frame = main.build_prediction_records_dataframe([
        record({"id": "failed", "features": {"x": 1}, "status_code": 500}),
        record({"id": "empty", "features": [], "status_code": 200}),
    ])
    assert frame.empty


def test_drift_signals_are_deduplicated_and_replay_safe():
    signals = main.build_automatic_drift_signals([record(offset=7), record(offset=8)])
    assert signals == [{
        "model_version_id": "00000000-0000-0000-0000-000000000003",
        "idempotency_key": "automatic-drift:events:0:7:8:00000000-0000-0000-0000-000000000003",
    }]


def test_flush_persists_before_offset_commit(monkeypatch):
    consumer = FakeConsumer()
    persist = Mock(return_value=True)
    monkeypatch.setattr(main, "save_prediction_records_and_automatic_drift_signals", persist)

    assert main.flush_batch(consumer, [record(offset=41)])
    assert consumer.commits[0][0][0].offset == 42
    frame, signals = persist.call_args.args
    assert list(frame) == list(PREDICTION_RECORD_COLUMNS)
    assert signals[0]["idempotency_key"].endswith(":41:41:00000000-0000-0000-0000-000000000003")


def test_flush_does_not_commit_when_transaction_fails(monkeypatch):
    consumer = FakeConsumer()
    monkeypatch.setattr(main, "save_prediction_records_and_automatic_drift_signals", Mock(return_value=False))
    assert not main.flush_batch(consumer, [record()])
    assert consumer.commits == []


def test_flush_rejects_mixed_partitions():
    consumer = FakeConsumer()
    try:
        main.flush_batch(consumer, [record(partition=0), record(partition=1)])
    except ValueError as exc:
        assert "exactly one partition" in str(exc)
    else:
        raise AssertionError("Expected partition validation failure")
