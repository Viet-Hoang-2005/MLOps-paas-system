import json
import os
import signal
import threading
import time

from confluent_kafka import Consumer, KafkaError, TopicPartition
from src.batching import (
    build_automatic_drift_signals,
    build_prediction_records_dataframe,
)
from src.dead_letter import DeadLetter, DeadLetterQueue
from src.logging_utils import Summary, configure, get_logger, log_event
from src.models import KafkaRecord, KafkaRecordProcessingError, RetryState

# Script execution must configure logging before importing database modules,
# whose engine setup can emit lifecycle diagnostics.
if __name__ == "__main__":
    configure("consumer")

from src.database import (
    PermanentWriteError,
    TransientWriteError,
    init_db,
    persistence_summary,
    save_prediction_records_and_automatic_drift_signals,
)
from src.drift_outbox import (
    OUTBOX_POLL_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    run_dispatcher,
)

logger = get_logger(__name__)
commit_summary = Summary(logger, "offset_commit_summary")
retry_summary = Summary(logger, "partition_retry_summary")
broker_summary = Summary(logger, "broker_poll_summary")

REDPANDA_BROKERS = os.environ.get("REDPANDA_BROKERS", "localhost:19092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "mlops_paas_production_data")
KAFKA_TOPIC_RETRY_SECONDS = max(1, int(os.environ.get("KAFKA_TOPIC_RETRY_SECONDS", "5")))
KAFKA_BATCH_SIZE = max(1, int(os.environ.get("KAFKA_BATCH_SIZE", "500")))
KAFKA_DB_RETRY_INITIAL_SECONDS = max(1, int(os.environ.get("KAFKA_DB_RETRY_INITIAL_SECONDS", "5")))
KAFKA_DB_RETRY_MAX_SECONDS = max(
    KAFKA_DB_RETRY_INITIAL_SECONDS,
    int(os.environ.get("KAFKA_DB_RETRY_MAX_SECONDS", "60")),
)
KAFKA_DB_RETRY_MAX_ATTEMPTS = max(1, int(os.environ.get("KAFKA_DB_RETRY_MAX_ATTEMPTS", "5")))
# Records that cannot be stored are parked here instead of being dropped. An empty
# value disables the dead-letter topic and restores drop-and-log behaviour.
KAFKA_DLQ_TOPIC = os.environ.get("KAFKA_DLQ_TOPIC", f"{KAFKA_TOPIC}.dlq")
dead_letter = DeadLetterQueue(REDPANDA_BROKERS, KAFKA_DLQ_TOPIC)

RUNNING = True
DISPATCHER_JOIN_TIMEOUT_SECONDS = REQUEST_TIMEOUT_SECONDS + OUTBOX_POLL_SECONDS + 1


def handle_sigterm(*args):
    global RUNNING
    log_event(logger, "INFO", "shutdown_requested", "Consumer shutdown requested")
    RUNNING = False


def _run_outbox_dispatcher(stop_event: threading.Event) -> None:
    try:
        run_dispatcher(stop_event)
    except Exception as exc:
        log_event(
            logger,
            "ERROR",
            "drift_dispatcher_failed",
            "Automatic drift dispatcher stopped unexpectedly",
            error_type=type(exc).__name__,
        )


def start_outbox_dispatcher() -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()
    dispatcher = threading.Thread(
        target=_run_outbox_dispatcher,
        args=(stop_event,),
        name="automatic-drift-outbox",
        daemon=True,
    )
    dispatcher.start()
    return stop_event, dispatcher


def ensure_outbox_dispatcher_running(dispatcher: threading.Thread) -> None:
    if not dispatcher.is_alive():
        raise RuntimeError("Automatic drift outbox dispatcher stopped unexpectedly.")


def _commit_batch_offset(consumer, record: KafkaRecord) -> bool:
    """Synchronously commit exactly one processed partition position."""
    next_offset = TopicPartition(record.topic, record.partition, record.offset + 1)
    started = time.perf_counter()
    failure_key = f"{record.topic}:{record.partition}"
    try:
        committed_offsets = consumer.commit(offsets=[next_offset], asynchronous=False)
    except Exception as exc:
        commit_summary.record(success=False, duration_ms=(time.perf_counter() - started) * 1000)
        commit_summary.failure(
            failure_key,
            "Kafka offset commit failed",
            error_type=type(exc).__name__,
            partition=record.partition,
            offset=record.offset + 1,
        )
        return False

    failures = [offset for offset in committed_offsets or [] if getattr(offset, "error", None)]
    if failures:
        commit_summary.record(success=False, duration_ms=(time.perf_counter() - started) * 1000)
        commit_summary.failure(
            failure_key,
            "Kafka offset commit returned errors",
            partition=record.partition,
            offset=record.offset + 1,
            count=len(failures),
        )
        return False
    commit_summary.record(duration_ms=(time.perf_counter() - started) * 1000, committed=1)
    commit_summary.recovery(failure_key, partition=record.partition)
    return True


def flush_batch(consumer, records: list[KafkaRecord]) -> bool:
    """Persist a batch and its outbox signals before its Kafka offset."""
    if not records:
        return True
    partitions = {(record.topic, record.partition) for record in records}
    if len(partitions) != 1:
        raise ValueError("A Kafka batch must contain records from exactly one partition.")

    if not _save_records(records):
        return False
    if not _commit_batch_offset(consumer, records[-1]):
        return False
    return True


def _save_records(records: list[KafkaRecord]) -> bool:
    """Store records; a record the database can never accept is parked, not allowed to fail the rest.

    Returns False when the write should be retried. Raises TransientWriteError when the
    database is unavailable. Rows are idempotent (ON CONFLICT DO NOTHING), so saving the
    good half again on a later retry is harmless.
    """
    predictions = build_prediction_records_dataframe(records)
    signals = build_automatic_drift_signals(records)
    try:
        return bool(save_prediction_records_and_automatic_drift_signals(predictions, signals))
    except PermanentWriteError:
        if len(records) == 1:
            return _park_unstorable_record(records[0])
        middle = len(records) // 2
        return _save_records(records[:middle]) and _save_records(records[middle:])


def _park_unstorable_record(record: KafkaRecord) -> bool:
    if dead_letter.enabled:
        letter = DeadLetter(
            value=json.dumps(record.payload, default=str).encode("utf-8"),
            topic=record.topic,
            partition=record.partition,
            offset=record.offset,
            reason="unstorable_record",
        )
        if not dead_letter.publish([letter]):
            log_event(
                logger,
                "ERROR",
                "unstorable_record_dead_letter_failed",
                "Batch kept for retry because a record could not be parked in the dead-letter topic",
                topic=record.topic,
                partition=record.partition,
                offset=record.offset,
            )
            return False
        log_event(
            logger,
            "ERROR",
            "unstorable_record_dead_lettered",
            "Record rejected by the database was moved to the dead-letter topic",
            topic=record.topic,
            partition=record.partition,
            offset=record.offset,
            dead_letter_topic=dead_letter.topic,
        )
        return True
    log_event(
        logger,
        "ERROR",
        "unstorable_record_dropped",
        "Record rejected by the database was dropped because the dead-letter topic is disabled",
        topic=record.topic,
        partition=record.partition,
        offset=record.offset,
        data_loss=True,
    )
    return True


def _partition_handle(key: tuple[str, int]) -> TopicPartition:
    return TopicPartition(key[0], key[1])


def _retry_delay(attempts: int) -> int:
    return min(
        KAFKA_DB_RETRY_INITIAL_SECONDS * (2 ** max(0, attempts - 1)),
        KAFKA_DB_RETRY_MAX_SECONDS,
    )


def _schedule_retry(
    consumer, key: tuple[str, int], retries: dict[tuple[str, int], RetryState], counted: bool = True
) -> None:
    retry = retries.setdefault(key, RetryState())
    retry.attempts += 1
    if counted:
        retry.failures += 1
    delay = _retry_delay(retry.attempts)
    retry.next_retry_at = time.monotonic() + delay
    if retry.attempts == 1:
        consumer.pause([_partition_handle(key)])
    retry_summary.record(success=False)
    retry_summary.failure(
        f"{key[0]}:{key[1]}",
        "Partition batch retained for retry",
        partition=key[1],
        retry_seconds=delay,
        attempt=retry.attempts,
    )


def _release_unsaveable_batch(consumer, key: tuple[str, int], batch: list[KafkaRecord], attempts: int) -> bool:
    """Free a partition whose batch the database keeps rejecting.

    The batch is parked in the dead-letter topic first. If that fails the batch is
    kept (and retried later) rather than lost; only with the dead-letter topic
    disabled is it dropped, loudly.
    """
    if dead_letter.enabled:
        letters = [
            DeadLetter(
                value=json.dumps(record.payload, default=str).encode("utf-8"),
                topic=record.topic,
                partition=record.partition,
                offset=record.offset,
                reason="db_write_failed",
            )
            for record in batch
        ]
        if not dead_letter.publish(letters):
            log_event(
                logger,
                "ERROR",
                "partition_batch_dead_letter_failed",
                "Batch kept for retry because it could not be parked in the dead-letter topic",
                topic=key[0],
                partition=key[1],
                attempts=attempts,
                batch_size=len(batch),
            )
            return False
        log_event(
            logger,
            "ERROR",
            "partition_batch_dead_lettered",
            "Batch moved to the dead-letter topic after max DB retry attempts to unblock partition",
            topic=key[0],
            partition=key[1],
            attempts=attempts,
            batch_size=len(batch),
            dead_letter_topic=dead_letter.topic,
        )
    else:
        log_event(
            logger,
            "ERROR",
            "partition_batch_discarded_max_retries",
            "Discarding batch after reaching max DB retry attempts to unblock partition",
            topic=key[0],
            partition=key[1],
            attempts=attempts,
            batch_size=len(batch),
            data_loss=True,
        )
    if batch:
        _commit_batch_offset(consumer, batch[-1])
    return True


def flush_pending_batch(
    consumer,
    pending_batches: dict[tuple[str, int], list[KafkaRecord]],
    retries: dict[tuple[str, int], RetryState],
    key: tuple[str, int],
) -> bool:
    """Flush a retained partition batch and release it only after offset commit."""
    batch = pending_batches[key]
    try:
        saved = flush_batch(consumer, batch)
    except TransientWriteError:
        # The database is down: keep the batch and wait, however long it takes.
        _schedule_retry(consumer, key, retries, counted=False)
        return False
    if not saved:
        retry = retries.get(key)
        failed_attempts = (retry.failures if retry else 0) + 1
        if failed_attempts >= KAFKA_DB_RETRY_MAX_ATTEMPTS:
            if _release_unsaveable_batch(consumer, key, batch, failed_attempts):
                pending_batches.pop(key, None)
                was_paused = retries.pop(key, None)
                if was_paused:
                    consumer.resume([_partition_handle(key)])
                return False

        _schedule_retry(consumer, key, retries)
        return False

    pending_batches.pop(key)
    was_paused = retries.pop(key, None)
    if was_paused:
        consumer.resume([_partition_handle(key)])
        retry_summary.recovery(f"{key[0]}:{key[1]}", partition=key[1])
    return True


def skip_corrupt_record(
    consumer,
    pending_batches: dict[tuple[str, int], list[KafkaRecord]],
    retries: dict[tuple[str, int], RetryState],
    msg,
    error: Exception,
) -> bool:
    """Skip a malformed record without committing past unsaved records before it.

    A Kafka offset commit covers every earlier offset in the partition, so the
    corrupt record may only be committed once the partition has no retained
    batch. Otherwise a restart would resume after records that were never
    persisted. When the batch cannot be flushed the record stays uncommitted:
    the next committed batch (or a replay after restart) moves past it.
    """
    key = (msg.topic(), msg.partition())
    log_event(
        logger,
        "ERROR",
        "consumer_corrupt_message_skipped",
        "Malformed Kafka record skipped to prevent poison pill crash loop",
        topic=key[0],
        partition=key[1],
        offset=msg.offset(),
        error_type=type(error).__name__,
    )
    if pending_batches.get(key) and key not in retries:
        try:
            flush_pending_batch(consumer, pending_batches, retries, key)
        except Exception as flush_err:
            log_event(
                logger,
                "ERROR",
                "consumer_pending_flush_failed",
                "Failed to flush pending batch before skipping corrupt record",
                error_type=type(flush_err).__name__,
            )
    # A batch dropped after max retries is already released, so only a batch
    # that is still retained blocks the skip.
    if pending_batches.get(key):
        log_event(
            logger,
            "WARNING",
            "consumer_corrupt_message_commit_deferred",
            "Corrupt record left uncommitted until the retained batch is saved",
            topic=key[0],
            partition=key[1],
            offset=msg.offset(),
        )
        return False
    if dead_letter.enabled:
        letter = DeadLetter(
            value=msg.value() or b"",
            topic=key[0],
            partition=key[1],
            offset=msg.offset(),
            reason=f"malformed_record:{type(error).__name__}",
        )
        if not dead_letter.publish([letter]):
            log_event(
                logger,
                "ERROR",
                "consumer_corrupt_message_dead_letter_failed",
                "Corrupt record left uncommitted because it could not be parked in the dead-letter topic",
                topic=key[0],
                partition=key[1],
                offset=msg.offset(),
            )
            return False
    try:
        next_offset = TopicPartition(key[0], key[1], msg.offset() + 1)
        consumer.commit(offsets=[next_offset], asynchronous=False)
    except Exception as commit_err:
        log_event(
            logger,
            "ERROR",
            "consumer_corrupt_message_commit_failed",
            "Failed to commit offset after malformed record",
            error_type=type(commit_err).__name__,
        )
        return False
    return True


def main():
    configure("consumer")
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    conf = {
        "bootstrap.servers": REDPANDA_BROKERS,
        "group.id": "paas-db-writer-group",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
    }

    init_db()
    dispatcher_stop, dispatcher = start_outbox_dispatcher()
    consumer = None
    pending_batches: dict[tuple[str, int], list[KafkaRecord]] = {}
    retries: dict[tuple[str, int], RetryState] = {}
    try:
        consumer = Consumer(conf)
        consumer.subscribe([KAFKA_TOPIC])
        log_event(logger, "INFO", "consumer_started", "Consumer subscribed and listening")

        while RUNNING:
            ensure_outbox_dispatcher_running(dispatcher)
            now = time.monotonic()
            for key, retry in list(retries.items()):
                if now >= retry.next_retry_at:
                    flush_pending_batch(consumer, pending_batches, retries, key)

            msg = consumer.poll(timeout=1.0)

            if msg is None:
                for key in list(pending_batches):
                    if key in retries:
                        continue
                    flush_pending_batch(consumer, pending_batches, retries, key)
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                if msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART or msg.error().retriable():
                    broker_summary.failure(
                        "poll",
                        "Kafka temporarily unavailable",
                        error_code=msg.error().code(),
                        retry_seconds=KAFKA_TOPIC_RETRY_SECONDS,
                    )
                    time.sleep(KAFKA_TOPIC_RETRY_SECONDS)
                    continue
                raise RuntimeError(f"Kafka consumer error: {msg.error()}")

            broker_summary.recovery("poll")
            try:
                val_json = msg.value().decode("utf-8")
                row_data = json.loads(val_json)
                if not isinstance(row_data, dict):
                    raise ValueError(f"Payload must be a JSON object, got {type(row_data).__name__}")
                record = KafkaRecord(
                    payload=row_data,
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                )
                key = (record.topic, record.partition)
                current_batch = pending_batches.setdefault(key, [])
                current_batch.append(record)

                if key not in retries and len(current_batch) >= KAFKA_BATCH_SIZE:
                    flush_pending_batch(consumer, pending_batches, retries, key)

            except Exception as parse_e:
                skip_corrupt_record(consumer, pending_batches, retries, msg, parse_e)

    except KeyboardInterrupt:
        log_event(logger, "INFO", "shutdown_requested", "Consumer shutdown requested")
    finally:
        try:
            if consumer is not None:
                for key in list(pending_batches):
                    flush_pending_batch(consumer, pending_batches, retries, key)
        finally:
            dispatcher_stop.set()
            dispatcher.join(timeout=DISPATCHER_JOIN_TIMEOUT_SECONDS)
            if dispatcher.is_alive():
                log_event(
                    logger,
                    "WARNING",
                    "dispatcher_shutdown_timeout",
                    "Drift dispatcher shutdown timed out; leased rows remain retryable",
                )
            try:
                if consumer is not None:
                    consumer.close()
            finally:
                for summary in (
                    persistence_summary,
                    commit_summary,
                    retry_summary,
                    broker_summary,
                ):
                    summary.close()
        log_event(logger, "INFO", "consumer_stopped", "Consumer cleanup finished")


def run():
    """Process entry point with one safe diagnostic for terminal failures."""
    configure("consumer")
    log_event(logger, "INFO", "consumer_starting", "Waiting for broker startup")
    time.sleep(5)
    try:
        main()
    except KafkaRecordProcessingError as exc:
        log_event(
            logger,
            "ERROR",
            "consumer_record_processing_failed",
            "Kafka record processing failed; offset retained",
            operation="record_parse",
            error_type=exc.error_type,
        )
        raise SystemExit(1) from None
    except Exception as exc:
        log_event(
            logger,
            "ERROR",
            "consumer_failed",
            "Consumer stopped after an unrecoverable error",
            error_type=type(exc).__name__,
            exc_info=True,
        )
        raise SystemExit(1) from None
