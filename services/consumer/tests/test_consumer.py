import json
from unittest.mock import Mock

import pytest
from src import kafka_runtime as main
from src.batching import PREDICTION_RECORD_COLUMNS, is_production_sample
from src.models import KafkaRecord


class FakeConsumer:
    def __init__(self):
        self.commits = []
        self.paused = []
        self.resumed = []

    def commit(self, offsets, asynchronous):
        self.commits.append((offsets, asynchronous))
        return []

    def pause(self, partitions):
        self.paused.extend(partitions)

    def resume(self, partitions):
        self.resumed.extend(partitions)


class FakeDeadLetter:
    def __init__(self, enabled=True, succeeds=True):
        self.enabled = enabled
        self.succeeds = succeeds
        self.topic = "events.dlq"
        self.published = []

    def publish(self, letters):
        if not self.succeeds:
            return False
        self.published.extend(letters)
        return True


@pytest.fixture(autouse=True)
def dead_letter(monkeypatch):
    fake = FakeDeadLetter()
    monkeypatch.setattr(main, "dead_letter", fake)
    return fake


def record(payload=None, offset=0, partition=0):
    return KafkaRecord(
        payload
        or {
            "id": "00000000-0000-0000-0000-000000000001",
            "project_id": "00000000-0000-0000-0000-000000000002",
            "model_version_id": "00000000-0000-0000-0000-000000000003",
            "timestamp": "2026-01-01T00:00:00Z",
            "features": {"x": 1},
            "prediction": "safe",
            "confidence": 80.0,
            "status_code": 200,
        },
        topic="events",
        partition=partition,
        offset=offset,
    )


def test_prediction_batch_keeps_only_owned_schema_fields():
    frame = main.build_prediction_records_dataframe([record()])
    assert list(frame) == list(PREDICTION_RECORD_COLUMNS)
    assert frame.loc[0, "public_id"] == "00000000-0000-0000-0000-000000000001"
    assert "tenant_id" not in frame and "status_code" not in frame


def test_prediction_batch_excludes_failed_or_featureless_events():
    frame = main.build_prediction_records_dataframe(
        [
            record({"id": "failed", "features": {"x": 1}, "status_code": 500}),
            record({"id": "empty", "features": [], "status_code": 200}),
        ]
    )
    assert frame.empty


def test_drift_signals_are_deduplicated_and_replay_safe():
    signals = main.build_automatic_drift_signals([record(offset=7), record(offset=8)])
    assert signals == [
        {
            "model_version_id": "00000000-0000-0000-0000-000000000003",
            "idempotency_key": "automatic-drift:events:0:7:8:00000000-0000-0000-0000-000000000003",
        }
    ]


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
    monkeypatch.setattr(
        main,
        "save_prediction_records_and_automatic_drift_signals",
        Mock(return_value=False),
    )
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

def test_is_production_sample_rejects_non_uuid():
    valid = {
        "id": "00000000-0000-0000-0000-000000000001",
        "project_id": "00000000-0000-0000-0000-000000000002",
        "model_version_id": "00000000-0000-0000-0000-000000000003",
        "features": {"x": 1},
        "status_code": 200,
    }
    assert is_production_sample(valid)

    # Invalid event_id
    assert not is_production_sample(valid | {"id": "not-a-uuid"})
    # Invalid project_id
    assert not is_production_sample(valid | {"project_id": "not-a-uuid"})
    # Invalid model_version_id
    assert not is_production_sample(valid | {"model_version_id": "not-a-uuid"})
    # Non-dict payload
    assert not is_production_sample("string_payload")
    # Non-dict features
    assert not is_production_sample(valid | {"features": "not-a-dict"})


def test_flush_pending_batch_dead_letters_after_max_retries(monkeypatch, dead_letter):
    from src.models import RetryState

    consumer = FakeConsumer()
    monkeypatch.setattr(
        main,
        "save_prediction_records_and_automatic_drift_signals",
        Mock(return_value=False),
    )
    key = ("events", 0)
    pending = {key: [record(offset=10)]}
    retries = {key: RetryState(attempts=main.KAFKA_DB_RETRY_MAX_ATTEMPTS, failures=main.KAFKA_DB_RETRY_MAX_ATTEMPTS)}

    result = main.flush_pending_batch(consumer, pending, retries, key)
    assert not result
    assert key not in pending
    assert key not in retries
    # Should commit offset 11 (offset 10 + 1) to unblock partition
    assert len(consumer.commits) == 1
    assert consumer.commits[0][0][0].offset == 11
    # Should resume the partition
    assert len(consumer.resumed) == 1
    assert consumer.resumed[0].partition == 0
    # The batch is parked, not lost
    assert [(letter.offset, letter.reason) for letter in dead_letter.published] == [(10, "db_write_failed")]
    assert json.loads(dead_letter.published[0].value)["prediction"] == "safe"


def corrupt_message(offset, partition=0):
    msg = Mock()
    msg.topic.return_value = "events"
    msg.partition.return_value = partition
    msg.offset.return_value = offset
    return msg


def test_corrupt_record_commits_after_pending_batch_is_saved(monkeypatch):
    consumer = FakeConsumer()
    monkeypatch.setattr(
        main,
        "save_prediction_records_and_automatic_drift_signals",
        Mock(return_value=True),
    )
    key = ("events", 0)
    pending = {key: [record(offset=4)]}

    assert main.skip_corrupt_record(consumer, pending, {}, corrupt_message(5), ValueError("bad"))
    assert key not in pending
    # Batch commit (offset 5) followed by the skip commit (offset 6).
    assert [c[0][0].offset for c in consumer.commits] == [5, 6]


def test_corrupt_record_does_not_commit_past_unsaved_batch(monkeypatch):
    consumer = FakeConsumer()
    monkeypatch.setattr(
        main,
        "save_prediction_records_and_automatic_drift_signals",
        Mock(return_value=False),
    )
    key = ("events", 0)
    pending = {key: [record(offset=4)]}
    retries = {}

    assert not main.skip_corrupt_record(consumer, pending, retries, corrupt_message(5), ValueError("bad"))
    assert consumer.commits == []
    assert len(pending[key]) == 1
    assert retries[key].attempts == 1


def test_corrupt_record_does_not_force_flush_during_retry_backoff(monkeypatch):
    from src.models import RetryState

    consumer = FakeConsumer()
    save = Mock(return_value=False)
    monkeypatch.setattr(main, "save_prediction_records_and_automatic_drift_signals", save)
    key = ("events", 0)
    pending = {key: [record(offset=4)]}
    retries = {key: RetryState(attempts=2, failures=2)}

    assert not main.skip_corrupt_record(consumer, pending, retries, corrupt_message(5), ValueError("bad"))
    save.assert_not_called()
    assert retries[key].attempts == 2
    assert consumer.commits == []


def test_corrupt_record_commits_when_partition_has_no_batch():
    consumer = FakeConsumer()

    assert main.skip_corrupt_record(consumer, {}, {}, corrupt_message(7), ValueError("bad"))
    assert [c[0][0].offset for c in consumer.commits] == [8]


def _failing_save(monkeypatch):
    monkeypatch.setattr(
        main,
        "save_prediction_records_and_automatic_drift_signals",
        Mock(return_value=False),
    )


def test_batch_stays_retained_when_dead_letter_publish_fails(monkeypatch, dead_letter):
    from src.models import RetryState

    dead_letter.succeeds = False
    consumer = FakeConsumer()
    _failing_save(monkeypatch)
    key = ("events", 0)
    pending = {key: [record(offset=10)]}
    retries = {key: RetryState(attempts=main.KAFKA_DB_RETRY_MAX_ATTEMPTS, failures=main.KAFKA_DB_RETRY_MAX_ATTEMPTS)}

    assert not main.flush_pending_batch(consumer, pending, retries, key)
    assert len(pending[key]) == 1
    assert retries[key].attempts == main.KAFKA_DB_RETRY_MAX_ATTEMPTS + 1
    assert consumer.commits == []
    assert consumer.resumed == []


def test_batch_is_dropped_loudly_only_when_dead_letter_is_disabled(monkeypatch, dead_letter):
    from src.models import RetryState

    dead_letter.enabled = False
    consumer = FakeConsumer()
    _failing_save(monkeypatch)
    key = ("events", 0)
    pending = {key: [record(offset=10)]}
    retries = {key: RetryState(attempts=main.KAFKA_DB_RETRY_MAX_ATTEMPTS, failures=main.KAFKA_DB_RETRY_MAX_ATTEMPTS)}

    assert not main.flush_pending_batch(consumer, pending, retries, key)
    assert key not in pending
    assert dead_letter.published == []
    assert consumer.commits[0][0][0].offset == 11


def test_batch_is_dropped_after_exactly_max_attempts(monkeypatch, dead_letter):
    consumer = FakeConsumer()
    _failing_save(monkeypatch)
    key = ("events", 0)
    pending = {key: [record(offset=3)]}
    retries = {}

    for _ in range(main.KAFKA_DB_RETRY_MAX_ATTEMPTS - 1):
        main.flush_pending_batch(consumer, pending, retries, key)
        assert key in pending
    main.flush_pending_batch(consumer, pending, retries, key)
    assert key not in pending
    assert len(dead_letter.published) == 1


def test_corrupt_record_is_parked_before_its_offset_is_committed(dead_letter):
    consumer = FakeConsumer()
    msg = corrupt_message(7)
    msg.value.return_value = b"{not json"

    assert main.skip_corrupt_record(consumer, {}, {}, msg, ValueError("bad"))
    assert [c[0][0].offset for c in consumer.commits] == [8]
    letter = dead_letter.published[0]
    assert (letter.value, letter.offset, letter.reason) == (b"{not json", 7, "malformed_record:ValueError")


def test_corrupt_record_is_not_committed_when_dead_letter_publish_fails(dead_letter):
    dead_letter.succeeds = False
    consumer = FakeConsumer()
    msg = corrupt_message(7)
    msg.value.return_value = b"{not json"

    assert not main.skip_corrupt_record(consumer, {}, {}, msg, ValueError("bad"))
    assert consumer.commits == []


def _batch(count, start=0):
    return [
        record(
            payload={
                "id": f"00000000-0000-0000-0000-{index:012d}",
                "project_id": "00000000-0000-0000-0000-000000000002",
                "model_version_id": "00000000-0000-0000-0000-000000000003",
                "timestamp": "2026-01-01T00:00:00Z",
                "features": {"x": index},
                "prediction": "safe",
                "confidence": 80.0,
                "status_code": 200,
            },
            offset=index,
        )
        for index in range(start, start + count)
    ]


def _saver(monkeypatch, bad_offsets=(), stored=None):
    """Fake database that rejects any write containing a record from `bad_offsets`."""
    from src.database import PermanentWriteError

    stored = stored if stored is not None else []

    def save(predictions, signals):
        offsets = [int(value) for value in (row["x"] for row in predictions["features"])] if len(predictions) else []
        if set(offsets) & set(bad_offsets):
            raise PermanentWriteError("DataError")
        stored.extend(offsets)
        return True

    monkeypatch.setattr(main, "save_prediction_records_and_automatic_drift_signals", save)
    return stored


def test_one_unstorable_record_does_not_take_the_rest_of_the_batch_with_it(monkeypatch, dead_letter):
    stored = _saver(monkeypatch, bad_offsets={7}, stored=[])
    consumer = FakeConsumer()
    batch = _batch(20)

    assert main.flush_batch(consumer, batch)

    assert sorted(set(stored)) == [i for i in range(20) if i != 7]
    assert [(letter.offset, letter.reason) for letter in dead_letter.published] == [(7, "unstorable_record")]
    assert [c[0][0].offset for c in consumer.commits] == [20]


def test_several_unstorable_records_are_each_parked(monkeypatch, dead_letter):
    stored = _saver(monkeypatch, bad_offsets={0, 13, 19}, stored=[])
    consumer = FakeConsumer()

    assert main.flush_batch(consumer, _batch(20))

    assert sorted(set(stored)) == [i for i in range(20) if i not in {0, 13, 19}]
    assert sorted(letter.offset for letter in dead_letter.published) == [0, 13, 19]


def test_batch_is_not_committed_when_an_unstorable_record_cannot_be_parked(monkeypatch, dead_letter):
    _saver(monkeypatch, bad_offsets={3}, stored=[])
    dead_letter.succeeds = False
    consumer = FakeConsumer()

    assert not main.flush_batch(consumer, _batch(8))
    assert consumer.commits == []


def test_unstorable_record_is_dropped_loudly_only_without_a_dead_letter_topic(monkeypatch, dead_letter):
    dead_letter.enabled = False
    stored = _saver(monkeypatch, bad_offsets={3}, stored=[])
    consumer = FakeConsumer()

    assert main.flush_batch(consumer, _batch(8))
    assert 3 not in stored and len(set(stored)) == 7


def test_database_outage_never_sends_the_batch_to_the_dead_letter_topic(monkeypatch, dead_letter):
    from src.database import TransientWriteError

    def down(predictions, signals):
        raise TransientWriteError("OperationalError")

    monkeypatch.setattr(main, "save_prediction_records_and_automatic_drift_signals", down)
    consumer = FakeConsumer()
    key = ("events", 0)
    pending = {key: _batch(5)}
    retries = {}

    # Far more attempts than KAFKA_DB_RETRY_MAX_ATTEMPTS: an outage is not a poisoned batch.
    for _ in range(main.KAFKA_DB_RETRY_MAX_ATTEMPTS * 4):
        assert not main.flush_pending_batch(consumer, pending, retries, key)

    assert len(pending[key]) == 5
    assert dead_letter.published == []
    assert consumer.commits == []
    assert retries[key].attempts == main.KAFKA_DB_RETRY_MAX_ATTEMPTS * 4
    assert retries[key].failures == 0  # backoff keeps growing, but nothing counts towards giving up


def test_batch_saves_normally_once_the_database_is_back(monkeypatch, dead_letter):
    from src.database import TransientWriteError

    calls = {"count": 0}
    stored = []

    def flaky(predictions, signals):
        calls["count"] += 1
        if calls["count"] <= 3:
            raise TransientWriteError("OperationalError")
        stored.extend(predictions["public_id"])
        return True

    monkeypatch.setattr(main, "save_prediction_records_and_automatic_drift_signals", flaky)
    consumer = FakeConsumer()
    key = ("events", 0)
    pending = {key: _batch(4)}
    retries = {}

    for _ in range(3):
        assert not main.flush_pending_batch(consumer, pending, retries, key)
    assert main.flush_pending_batch(consumer, pending, retries, key)

    assert key not in pending and key not in retries
    assert len(stored) == 4
    assert [c[0][0].offset for c in consumer.commits] == [4]
