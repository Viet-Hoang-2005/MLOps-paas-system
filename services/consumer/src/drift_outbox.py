"""Deliver durable automatic-drift signals without blocking Kafka ingestion."""

import os
import threading
import time

import requests
from sqlalchemy.exc import SQLAlchemyError
from src.logging_utils import Summary, get_logger, log_event

logger = get_logger(__name__)
delivery_summary = Summary(logger, "drift_signal_delivery_summary")
database_summary = Summary(logger, "drift_outbox_database_summary")

from src.database import (
    claim_automatic_drift_signals,
    mark_automatic_drift_signal_published,
    reschedule_automatic_drift_signal,
)


CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL = os.environ.get(
    "CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL", ""
).strip()
WEBHOOK_SECRET = os.environ.get("CONTROL_PLANE_WEBHOOK_SECRET", "")
OUTBOX_POLL_SECONDS = max(1, int(os.environ.get("AUTOMATIC_DRIFT_OUTBOX_POLL_SECONDS", "5")))
OUTBOX_BATCH_SIZE = max(1, int(os.environ.get("AUTOMATIC_DRIFT_OUTBOX_BATCH_SIZE", "50")))
OUTBOX_LEASE_SECONDS = max(OUTBOX_POLL_SECONDS, int(os.environ.get("AUTOMATIC_DRIFT_OUTBOX_LEASE_SECONDS", "60")))
OUTBOX_RETRY_INITIAL_SECONDS = max(
    1, int(os.environ.get("AUTOMATIC_DRIFT_OUTBOX_RETRY_INITIAL_SECONDS", "5"))
)
OUTBOX_RETRY_MAX_SECONDS = max(
    OUTBOX_RETRY_INITIAL_SECONDS,
    int(os.environ.get("AUTOMATIC_DRIFT_OUTBOX_RETRY_MAX_SECONDS", "300")),
)
REQUEST_TIMEOUT_SECONDS = max(
    1, int(os.environ.get("AUTOMATIC_DRIFT_OUTBOX_REQUEST_TIMEOUT_SECONDS", "10"))
)


def retry_delay(attempts: int) -> int:
    return min(
        OUTBOX_RETRY_INITIAL_SECONDS * (2 ** max(0, attempts - 1)),
        OUTBOX_RETRY_MAX_SECONDS,
    )


def deliver(signal: dict) -> tuple[bool, str]:
    """Send one idempotent signal without exposing response payloads in logs."""
    if not CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL:
        return False, "CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL is not configured"
    if not WEBHOOK_SECRET:
        return False, "CONTROL_PLANE_WEBHOOK_SECRET is not configured"

    try:
        response = requests.post(
            CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL,
            headers={
                "Authorization": f"Bearer {WEBHOOK_SECRET}",
                "Content-Type": "application/json",
                "Idempotency-Key": signal["idempotency_key"],
            },
            json={"model_version_id": signal["model_version_id"]},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return False, f"request failed: {exc.__class__.__name__}"

    if 200 <= response.status_code < 300:
        return True, ""
    return False, f"control-plane returned HTTP {response.status_code}"


def drain_once() -> int:
    delivered = 0
    failed = False
    for event in claim_automatic_drift_signals(OUTBOX_BATCH_SIZE, OUTBOX_LEASE_SECONDS):
        started = time.perf_counter()
        success, error = deliver(event)
        if success:
            mark_automatic_drift_signal_published(event["id"])
            delivered += 1
            delivery_summary.record(duration_ms=(time.perf_counter() - started) * 1000, published=1)
            continue

        delay = retry_delay(event["attempts"])
        reschedule_automatic_drift_signal(event["id"], event["attempts"], error, delay)
        failed = True
        delivery_summary.record(success=False, duration_ms=(time.perf_counter() - started) * 1000)
        delivery_summary.failure("delivery", "Automatic drift signal delivery failed; retry scheduled", retry_seconds=delay, attempt=event["attempts"])
    if delivered and not failed:
        delivery_summary.recovery("delivery")
    return delivered


def run_dispatcher(stop_event: threading.Event) -> None:
    """Drain the outbox until shutdown; unexpected errors terminate supervision."""
    log_event(logger, "INFO", "drift_dispatcher_started", "Automatic drift dispatcher started")
    try:
        _dispatch_until_stopped(stop_event)
    finally:
        delivery_summary.close()
        database_summary.close()


def _dispatch_until_stopped(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            delivered = drain_once()
            database_summary.recovery("database")
        except SQLAlchemyError as exc:
            database_summary.failure("database", "Drift outbox database operation failed", error_type=type(exc).__name__, retry_seconds=OUTBOX_POLL_SECONDS)
            stop_event.wait(OUTBOX_POLL_SECONDS)
            continue

        if delivered:
            continue
        stop_event.wait(OUTBOX_POLL_SECONDS)
