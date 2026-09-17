from types import SimpleNamespace
from unittest.mock import Mock

from src import drift_outbox, kafka_runtime as main


def test_offset_error_objects_are_not_logged(monkeypatch):
    summary = Mock()
    consumer = Mock()
    consumer.commit.return_value = [SimpleNamespace(error="hidden broker details")]
    monkeypatch.setattr(main, "commit_summary", summary)
    assert not main._commit_batch_offset(consumer, main.KafkaRecord({}, "events", 1, 7))
    summary.failure.assert_called_once_with(
        "events:1", "Kafka offset commit returned errors", partition=1, offset=8, count=1
    )


def test_webhook_outbox_retries_without_logging_response_payload(monkeypatch):
    summary = Mock()
    monkeypatch.setattr(drift_outbox, "delivery_summary", summary)
    monkeypatch.setattr(
        drift_outbox, "claim_automatic_drift_signals",
        lambda *_: [{"id": 1, "attempts": 2, "model_version_id": "version"}],
    )
    monkeypatch.setattr(drift_outbox, "deliver", Mock(return_value=(False, "private response-payload")))
    monkeypatch.setattr(drift_outbox, "reschedule_automatic_drift_signal", Mock())

    assert drift_outbox.drain_once() == 0
    assert "response-payload" not in str(summary.mock_calls)
