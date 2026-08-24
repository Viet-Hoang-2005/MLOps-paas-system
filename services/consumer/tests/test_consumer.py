import json
import threading
import pandas as pd
import pytest

from unittest.mock import Mock
from src import main


class FakeMessage:
    def __init__(self, payload=None, error=None, topic="events", partition=0, offset=0):
        self._payload = payload
        self._error = error
        self._topic = topic
        self._partition = partition
        self._offset = offset

    def value(self):
        return json.dumps(self._payload).encode()

    def error(self):
        return self._error

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset


class FakeConsumer:
    def __init__(self, messages):
        self.messages = list(messages)
        self.commits = 0
        self.commit_offsets = []
        self.commit_exception = None
        self.closed = False
        self.topics = None
        self.paused = []
        self.resumed = []

    def subscribe(self, topics):
        self.topics = topics

    def poll(self, timeout):
        if self.messages:
            return self.messages.pop(0)
        main.RUNNING = False
        return None

    def commit(self, offsets=None, asynchronous=True):
        if self.commit_exception:
            raise self.commit_exception
        self.commits += 1
        self.commit_offsets.append((offsets, asynchronous))
        return offsets

    def pause(self, partitions):
        self.paused.extend(partitions)

    def resume(self, partitions):
        self.resumed.extend(partitions)

    def close(self):
        self.closed = True


class FakeStopEvent:
    def __init__(self):
        self.was_set = False

    def set(self):
        self.was_set = True


class FakeDispatcher:
    def __init__(self, alive=True):
        self.alive = alive
        self.join_timeouts = []

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_timeouts.append(timeout)


def install_fake_dispatcher(monkeypatch, *, alive=True):
    stop_event = FakeStopEvent()
    dispatcher = FakeDispatcher(alive=alive)
    monkeypatch.setattr(main, "start_outbox_dispatcher", lambda: (stop_event, dispatcher))
    return stop_event, dispatcher


def record(payload=None, topic="events", partition=0, offset=0):
    return main.KafkaRecord(payload or {"model_version_id": "m"}, topic, partition, offset)


def test_build_batch_dataframe_converts_dates_to_utc():
    df = main.build_batch_dataframe([record({
        "timestamp": "2026-01-01T00:00:00Z", "created_at": "bad", "value": 1
    })])
    assert str(df["timestamp"].dtype) == "datetime64[ns, UTC]"
    assert pd.isna(df.loc[0, "created_at"])


def test_build_automatic_drift_signals_is_deduplicated_and_replay_safe():
    signals = main.build_automatic_drift_signals(
        [
            record({"model_version_id": "version-b"}, offset=7),
            record({"model_version_id": "version-a"}, offset=8),
            record({"model_version_id": "version-a"}, offset=9),
            record({"model_version_id": None}, offset=10),
        ]
    )

    assert signals == [
        {
            "model_version_id": "version-a",
            "idempotency_key": "automatic-drift:events:0:7:10:version-a",
        },
        {
            "model_version_id": "version-b",
            "idempotency_key": "automatic-drift:events:0:7:10:version-b",
        },
    ]


def test_flush_batch_commits_only_after_success(monkeypatch):
    consumer = FakeConsumer([])
    persist = Mock(return_value=False)
    monkeypatch.setattr(main, "save_dataframe_and_automatic_drift_signals", persist)
    assert not main.flush_batch(consumer, [record(offset=41)])
    assert consumer.commits == 0

    persist.return_value = True
    assert main.flush_batch(consumer, [record(offset=41)])
    assert consumer.commits == 1
    assert persist.call_args.args[1] == "paas_production_logs"
    assert persist.call_args.args[2] == [
        {"model_version_id": "m", "idempotency_key": "automatic-drift:events:0:41:41:m"}
    ]
    offsets, asynchronous = consumer.commit_offsets[0]
    assert asynchronous is False
    assert offsets[0].topic == "events"
    assert offsets[0].partition == 0
    assert offsets[0].offset == 42


def test_flush_empty_batch_is_noop():
    consumer = FakeConsumer([])
    assert main.flush_batch(consumer, [])
    assert consumer.commits == 0


def test_flush_batch_rejects_mixed_partitions(monkeypatch):
    consumer = FakeConsumer([])
    monkeypatch.setattr(main, "save_dataframe_and_automatic_drift_signals", Mock(return_value=True))
    with pytest.raises(ValueError, match="exactly one partition"):
        main.flush_batch(consumer, [record(partition=0), record(partition=1)])


def test_failed_partition_batch_is_retained_paused_and_retried(monkeypatch):
    consumer = FakeConsumer([])
    key = ("events", 0)
    pending = {key: [record(offset=7)]}
    retries = {}
    monkeypatch.setattr(main, "save_dataframe_and_automatic_drift_signals", Mock(side_effect=[False, True]))

    saved = main.flush_pending_batch(consumer, pending, retries, key)
    assert not saved and key in pending and key in retries
    assert consumer.commits == 0
    assert [(item.topic, item.partition) for item in consumer.paused] == [key]

    saved = main.flush_pending_batch(consumer, pending, retries, key)
    assert saved and key not in pending and key not in retries
    assert consumer.commits == 1
    assert [(item.topic, item.partition) for item in consumer.resumed] == [key]
    assert consumer.commit_offsets[0][0][0].offset == 8


def test_commit_failure_retains_batch_for_idempotent_retry(monkeypatch):
    consumer = FakeConsumer([])
    consumer.commit_exception = RuntimeError("broker unavailable")
    key = ("events", 0)
    pending = {key: [record(offset=12)]}
    retries = {}
    persist = Mock(return_value=True)
    monkeypatch.setattr(main, "save_dataframe_and_automatic_drift_signals", persist)

    saved = main.flush_pending_batch(consumer, pending, retries, key)
    assert not saved and key in pending and key in retries
    persist.assert_called_once()


def test_main_flushes_valid_message_and_closes(monkeypatch):
    fake = FakeConsumer(
        [FakeMessage({"id": "1", "model_version_id": "m", "timestamp": "2026-01-01"}), None]
    )
    monkeypatch.setattr(main, "Consumer", lambda conf: fake)
    monkeypatch.setattr(main.signal, "signal", lambda *args: None)
    monkeypatch.setattr(main, "init_db", Mock())
    monkeypatch.setattr(main, "save_dataframe_and_automatic_drift_signals", Mock(return_value=True))
    stop_event, dispatcher = install_fake_dispatcher(monkeypatch)
    main.RUNNING = True
    main.main()
    assert fake.topics == [main.KAFKA_TOPIC]
    assert fake.commits == 1
    assert fake.commit_offsets[0][0][0].offset == 1
    assert fake.closed
    assert stop_event.was_set
    assert dispatcher.join_timeouts == [main.DISPATCHER_JOIN_TIMEOUT_SECONDS]


def test_main_disables_automatic_offset_storage(monkeypatch):
    fake = FakeConsumer([])
    captured_conf = {}

    def create_consumer(conf):
        captured_conf.update(conf)
        return fake

    monkeypatch.setattr(main, "Consumer", create_consumer)
    monkeypatch.setattr(main.signal, "signal", lambda *args: None)
    monkeypatch.setattr(main, "init_db", Mock())
    install_fake_dispatcher(monkeypatch)
    main.RUNNING = True
    main.main()

    assert captured_conf["enable.auto.commit"] is False
    assert captured_conf["enable.auto.offset.store"] is False


def test_main_ignores_malformed_message(monkeypatch):
    bad = FakeMessage()
    bad.value = lambda: b"not-json"
    fake = FakeConsumer([bad])
    monkeypatch.setattr(main, "Consumer", lambda conf: fake)
    monkeypatch.setattr(main.signal, "signal", lambda *args: None)
    monkeypatch.setattr(main, "init_db", Mock())
    install_fake_dispatcher(monkeypatch)
    main.RUNNING = True
    with pytest.raises(RuntimeError, match="Error parsing Kafka payload"):
        main.main()
    assert fake.commits == 0 and fake.closed


def test_handle_sigterm_stops_loop():
    main.RUNNING = True
    main.handle_sigterm()
    assert main.RUNNING is False


def test_start_outbox_dispatcher_uses_supervised_daemon_thread(monkeypatch):
    started = threading.Event()

    def run(stop_event):
        started.set()
        stop_event.wait()

    monkeypatch.setattr(main, "run_dispatcher", run)

    stop_event, dispatcher = main.start_outbox_dispatcher()
    assert started.wait(timeout=1)
    assert dispatcher.name == "automatic-drift-outbox"
    assert dispatcher.daemon is True
    stop_event.set()
    dispatcher.join(timeout=1)
    assert not dispatcher.is_alive()


def test_dispatcher_delivery_wait_does_not_block_kafka_polling(monkeypatch):
    delivery_started = threading.Event()
    release_delivery = threading.Event()

    def blocked_delivery(_stop_event):
        delivery_started.set()
        release_delivery.wait(timeout=1)

    class PollingConsumer(FakeConsumer):
        def __init__(self):
            super().__init__([])
            self.was_polled = False

        def poll(self, timeout):
            assert delivery_started.wait(timeout=1)
            self.was_polled = True
            main.RUNNING = False
            release_delivery.set()
            return None

    consumer = PollingConsumer()
    monkeypatch.setattr(main, "run_dispatcher", blocked_delivery)
    monkeypatch.setattr(main, "Consumer", lambda _conf: consumer)
    monkeypatch.setattr(main.signal, "signal", lambda *args: None)
    monkeypatch.setattr(main, "init_db", Mock())
    main.RUNNING = True

    main.main()

    assert consumer.was_polled
    assert consumer.closed


def test_main_exits_when_dispatcher_stops_unexpectedly(monkeypatch):
    consumer = FakeConsumer([])
    monkeypatch.setattr(main, "Consumer", lambda _conf: consumer)
    monkeypatch.setattr(main.signal, "signal", lambda *args: None)
    monkeypatch.setattr(main, "init_db", Mock())
    stop_event, dispatcher = install_fake_dispatcher(monkeypatch, alive=False)
    main.RUNNING = True

    with pytest.raises(RuntimeError, match="dispatcher stopped unexpectedly"):
        main.main()

    assert stop_event.was_set
    assert dispatcher.join_timeouts == [main.DISPATCHER_JOIN_TIMEOUT_SECONDS]
    assert consumer.closed
