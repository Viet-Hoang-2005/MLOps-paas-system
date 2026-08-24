from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src import drift_outbox as dispatcher


def test_deliver_posts_internal_idempotent_signal(monkeypatch):
    monkeypatch.setattr(
        dispatcher,
        "CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL",
        "http://control-plane/internal/webhooks/automatic-drift/",
    )
    monkeypatch.setattr(dispatcher, "WEBHOOK_SECRET", "secret")
    post = Mock(return_value=SimpleNamespace(status_code=202))
    monkeypatch.setattr(dispatcher.requests, "post", post)

    assert dispatcher.deliver({"model_version_id": "version-1", "idempotency_key": "signal-1"}) == (True, "")
    post.assert_called_once_with(
        "http://control-plane/internal/webhooks/automatic-drift/",
        headers={
            "Authorization": "Bearer secret",
            "Content-Type": "application/json",
            "Idempotency-Key": "signal-1",
        },
        json={"model_version_id": "version-1"},
        timeout=dispatcher.REQUEST_TIMEOUT_SECONDS,
    )


def test_deliver_rejects_missing_configuration(monkeypatch):
    monkeypatch.setattr(dispatcher, "CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL", "")
    assert dispatcher.deliver({"model_version_id": "version-1", "idempotency_key": "signal-1"}) == (
        False,
        "CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL is not configured",
    )


def test_drain_marks_only_successful_signal_published(monkeypatch):
    signals = [
        {"id": 1, "model_version_id": "version-1", "idempotency_key": "signal-1", "attempts": 1},
        {"id": 2, "model_version_id": "version-2", "idempotency_key": "signal-2", "attempts": 2},
    ]
    monkeypatch.setattr(dispatcher, "claim_automatic_drift_signals", lambda *_args: signals)
    monkeypatch.setattr(dispatcher, "deliver", Mock(side_effect=[(True, ""), (False, "control plane unavailable")]))
    published = Mock()
    reschedule = Mock()
    monkeypatch.setattr(dispatcher, "mark_automatic_drift_signal_published", published)
    monkeypatch.setattr(dispatcher, "reschedule_automatic_drift_signal", reschedule)
    monkeypatch.setattr(dispatcher, "retry_delay", lambda attempts: attempts * 10)

    assert dispatcher.drain_once() == 1
    published.assert_called_once_with(1)
    reschedule.assert_called_once_with(2, 2, "control plane unavailable", 20)


def test_retry_delay_is_bounded(monkeypatch):
    monkeypatch.setattr(dispatcher, "OUTBOX_RETRY_INITIAL_SECONDS", 5)
    monkeypatch.setattr(dispatcher, "OUTBOX_RETRY_MAX_SECONDS", 30)
    assert dispatcher.retry_delay(1) == 5
    assert dispatcher.retry_delay(4) == 30


def test_dispatcher_retries_expected_database_errors(monkeypatch):
    stop_event = Mock()
    stop_event.is_set.side_effect = [False, False, True]
    drain = Mock(side_effect=[SQLAlchemyError("database unavailable"), 0])
    monkeypatch.setattr(dispatcher, "drain_once", drain)

    dispatcher.run_dispatcher(stop_event)

    assert drain.call_count == 2
    assert [call.args[0] for call in stop_event.wait.call_args_list] == [
        dispatcher.OUTBOX_POLL_SECONDS,
        dispatcher.OUTBOX_POLL_SECONDS,
    ]


def test_dispatcher_does_not_hide_unexpected_errors(monkeypatch):
    stop_event = Mock()
    stop_event.is_set.return_value = False
    monkeypatch.setattr(dispatcher, "drain_once", Mock(side_effect=RuntimeError("programming error")))

    with pytest.raises(RuntimeError, match="programming error"):
        dispatcher.run_dispatcher(stop_event)
