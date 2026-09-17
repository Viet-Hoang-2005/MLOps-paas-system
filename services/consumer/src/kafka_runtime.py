import os
import json
import time
import signal
import threading
from confluent_kafka import Consumer, KafkaError, TopicPartition
from src.batching import (
    build_automatic_drift_signals,
    build_prediction_records_dataframe,
)
from src.models import KafkaRecord, KafkaRecordProcessingError, RetryState
from src.logging_utils import Summary, configure, get_logger, log_event

# Script execution must configure logging before importing database modules,
# whose engine setup can emit lifecycle diagnostics.
if __name__ == "__main__":
    configure("consumer")

from src.database import (
    init_db,
    persistence_summary,
    save_prediction_records_and_automatic_drift_signals,
)
from src.drift_outbox import OUTBOX_POLL_SECONDS, REQUEST_TIMEOUT_SECONDS, run_dispatcher

logger = get_logger(__name__)
commit_summary = Summary(logger, "offset_commit_summary")
retry_summary = Summary(logger, "partition_retry_summary")
broker_summary = Summary(logger, "broker_poll_summary")

REDPANDA_BROKERS = os.environ.get('REDPANDA_BROKERS', 'localhost:19092')
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "mlops_paas_production_data")
KAFKA_TOPIC_RETRY_SECONDS = max(1, int(os.environ.get("KAFKA_TOPIC_RETRY_SECONDS", "5")))
KAFKA_BATCH_SIZE = max(1, int(os.environ.get("KAFKA_BATCH_SIZE", "500")))
KAFKA_DB_RETRY_INITIAL_SECONDS = max(1, int(os.environ.get("KAFKA_DB_RETRY_INITIAL_SECONDS", "5")))
KAFKA_DB_RETRY_MAX_SECONDS = max(
    KAFKA_DB_RETRY_INITIAL_SECONDS,
    int(os.environ.get("KAFKA_DB_RETRY_MAX_SECONDS", "60")),
)

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
        log_event(logger, "ERROR", "drift_dispatcher_failed", "Automatic drift dispatcher stopped unexpectedly", error_type=type(exc).__name__)


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
        commit_summary.failure(failure_key, "Kafka offset commit failed", error_type=type(exc).__name__, partition=record.partition, offset=record.offset + 1)
        return False

    failures = [offset for offset in committed_offsets or [] if getattr(offset, "error", None)]
    if failures:
        commit_summary.record(success=False, duration_ms=(time.perf_counter() - started) * 1000)
        commit_summary.failure(failure_key, "Kafka offset commit returned errors", partition=record.partition, offset=record.offset + 1, count=len(failures))
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

    predictions = build_prediction_records_dataframe(records)
    signals = build_automatic_drift_signals(records)
    if not save_prediction_records_and_automatic_drift_signals(predictions, signals):
        return False
    if not _commit_batch_offset(consumer, records[-1]):
        return False
    return True


def _partition_handle(key: tuple[str, int]) -> TopicPartition:
    return TopicPartition(key[0], key[1])


def _retry_delay(attempts: int) -> int:
    return min(
        KAFKA_DB_RETRY_INITIAL_SECONDS * (2 ** max(0, attempts - 1)),
        KAFKA_DB_RETRY_MAX_SECONDS,
    )


def _schedule_retry(consumer, key: tuple[str, int], retries: dict[tuple[str, int], RetryState]) -> None:
    retry = retries.setdefault(key, RetryState())
    retry.attempts += 1
    delay = _retry_delay(retry.attempts)
    retry.next_retry_at = time.monotonic() + delay
    if retry.attempts == 1:
        consumer.pause([_partition_handle(key)])
    retry_summary.record(success=False)
    retry_summary.failure(f"{key[0]}:{key[1]}", "Partition batch retained for retry", partition=key[1], retry_seconds=delay, attempt=retry.attempts)


def flush_pending_batch(
    consumer,
    pending_batches: dict[tuple[str, int], list[KafkaRecord]],
    retries: dict[tuple[str, int], RetryState],
    key: tuple[str, int],
) -> bool:
    """Flush a retained partition batch and release it only after offset commit."""
    batch = pending_batches[key]
    saved = flush_batch(consumer, batch)
    if not saved:
        _schedule_retry(consumer, key, retries)
        return False

    pending_batches.pop(key)
    was_paused = retries.pop(key, None)
    if was_paused:
        consumer.resume([_partition_handle(key)])
        retry_summary.recovery(f"{key[0]}:{key[1]}", partition=key[1])
    return True


def main():
    configure("consumer")
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    conf = {
        'bootstrap.servers': REDPANDA_BROKERS,
        'group.id': 'paas-db-writer-group',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False,
        'enable.auto.offset.store': False,
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
                    broker_summary.failure("poll", "Kafka temporarily unavailable", error_code=msg.error().code(), retry_seconds=KAFKA_TOPIC_RETRY_SECONDS)
                    time.sleep(KAFKA_TOPIC_RETRY_SECONDS)
                    continue
                raise RuntimeError(f"Kafka consumer error: {msg.error()}")
                    
            broker_summary.recovery("poll")
            try:
                val_json = msg.value().decode('utf-8')
                row_data = json.loads(val_json)
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
                raise KafkaRecordProcessingError(type(parse_e).__name__) from None
                
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
                log_event(logger, "WARNING", "dispatcher_shutdown_timeout", "Drift dispatcher shutdown timed out; leased rows remain retryable")
            try:
                if consumer is not None:
                    consumer.close()
            finally:
                for summary in (persistence_summary, commit_summary, retry_summary, broker_summary):
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
        log_event(logger, "ERROR", "consumer_failed", "Consumer stopped after an unrecoverable error", error_type=type(exc).__name__, exc_info=True)
        raise SystemExit(1) from None

