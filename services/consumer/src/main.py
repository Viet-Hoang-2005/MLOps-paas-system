import os
import json
import time
import signal
import threading
from dataclasses import dataclass
from typing import Any
import pandas as pd
from confluent_kafka import Consumer, KafkaError, TopicPartition
from src.database import (
    init_db,
    save_dataframe_and_automatic_drift_signals,
)
from src.drift_outbox import OUTBOX_POLL_SECONDS, REQUEST_TIMEOUT_SECONDS, run_dispatcher

# Lấy biến môi trường
REDPANDA_BROKERS = os.environ.get('REDPANDA_BROKERS', 'localhost:19092')
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "mlops_paas_production_data")
KAFKA_TOPIC_RETRY_SECONDS = max(1, int(os.environ.get("KAFKA_TOPIC_RETRY_SECONDS", "5")))
KAFKA_BATCH_SIZE = max(1, int(os.environ.get("KAFKA_BATCH_SIZE", "500")))
KAFKA_DB_RETRY_INITIAL_SECONDS = max(
    1, int(os.environ.get("KAFKA_DB_RETRY_INITIAL_SECONDS", "5"))
)
KAFKA_DB_RETRY_MAX_SECONDS = max(
    KAFKA_DB_RETRY_INITIAL_SECONDS,
    int(os.environ.get("KAFKA_DB_RETRY_MAX_SECONDS", "60")),
)
# Cờ báo hiệu trạng thái hoạt động
RUNNING = True
DISPATCHER_JOIN_TIMEOUT_SECONDS = REQUEST_TIMEOUT_SECONDS + OUTBOX_POLL_SECONDS + 1


@dataclass(frozen=True)
class KafkaRecord:
    """Application payload together with the Kafka position that owns it."""

    payload: dict[str, Any]
    topic: str
    partition: int
    offset: int


@dataclass
class RetryState:
    attempts: int = 0
    next_retry_at: float = 0.0

# Hàm xử lý tín hiệu dừng
def handle_sigterm(*args):
    global RUNNING
    print("Received SIGTERM. Shutting down gracefully...")
    RUNNING = False


def start_outbox_dispatcher() -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()
    dispatcher = threading.Thread(
        target=run_dispatcher,
        args=(stop_event,),
        name="automatic-drift-outbox",
        daemon=True,
    )
    dispatcher.start()
    return stop_event, dispatcher


def ensure_outbox_dispatcher_running(dispatcher: threading.Thread) -> None:
    if not dispatcher.is_alive():
        raise RuntimeError("Automatic drift outbox dispatcher stopped unexpectedly.")

def build_batch_dataframe(records: list[KafkaRecord]) -> pd.DataFrame:
    df = pd.DataFrame([record.payload for record in records])
    for column in ("timestamp", "created_at"):
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], utc=True, errors="coerce")
    return df


def build_automatic_drift_signals(records: list[KafkaRecord]) -> list[dict[str, str]]:
    """Create replay-safe outbox rows for every model represented in one batch."""
    if not records:
        return []
    first, last = records[0], records[-1]
    model_version_ids = {
        str(record.payload["model_version_id"])
        for record in records
        if record.payload.get("model_version_id")
    }
    batch_key = f"{first.topic}:{first.partition}:{first.offset}:{last.offset}"
    return [
        {
            "model_version_id": model_version_id,
            "idempotency_key": f"automatic-drift:{batch_key}:{model_version_id}",
        }
        for model_version_id in sorted(model_version_ids)
    ]


def _commit_batch_offset(consumer, record: KafkaRecord) -> bool:
    """Synchronously commit exactly one processed partition position."""
    next_offset = TopicPartition(record.topic, record.partition, record.offset + 1)
    try:
        committed_offsets = consumer.commit(offsets=[next_offset], asynchronous=False)
    except Exception as exc:
        print(
            f"[{record.topic}/{record.partition}] Kafka offset commit failed at "
            f"{record.offset + 1}: {exc}"
        )
        return False

    failures = [offset for offset in committed_offsets or [] if getattr(offset, "error", None)]
    if failures:
        print(
            f"[{record.topic}/{record.partition}] Kafka offset commit returned errors: "
            f"{failures}"
        )
        return False
    return True


def flush_batch(consumer, records: list[KafkaRecord]) -> bool:
    """Persist a batch and its outbox signals before its Kafka offset."""
    if not records:
        return True
    partitions = {(record.topic, record.partition) for record in records}
    if len(partitions) != 1:
        raise ValueError("A Kafka batch must contain records from exactly one partition.")

    dataframe = build_batch_dataframe(records)
    signals = build_automatic_drift_signals(records)
    if not save_dataframe_and_automatic_drift_signals(dataframe, "paas_production_logs", signals):
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
    print(
        f"[{key[0]}/{key[1]}] Database or offset commit failed; partition paused. "
        f"Retrying batch in {delay}s (attempt {retry.attempts})."
    )


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
    return True

# Hàm main để chạy Consumer liên tục lắng nghe Redpanda và xử lý dữ liệu
def main():
    # Đăng ký handler cho SIGTERM và SIGINT
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    # Cấu hình Kafka Consumer
    conf = {
        'bootstrap.servers': REDPANDA_BROKERS,
        'group.id': 'paas-db-writer-group',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False,
        # Store and commit offsets only after their PostgreSQL transaction succeeds.
        'enable.auto.offset.store': False,
    }

    init_db()
    dispatcher_stop, dispatcher = start_outbox_dispatcher()
    consumer = None
    pending_batches: dict[tuple[str, int], list[KafkaRecord]] = {}
    retries: dict[tuple[str, int], RetryState] = {}
    try:
        # Khởi tạo Consumer và subscribe vào topic
        consumer = Consumer(conf)
        consumer.subscribe([KAFKA_TOPIC])
        print(f"Consumer listening to the topic '{KAFKA_TOPIC}' at {REDPANDA_BROKERS}")

        while RUNNING:
            ensure_outbox_dispatcher_running(dispatcher)
            # Retry failed partitions without blocking heartbeats for the rest
            # of the consumer group. A partition remains paused until its
            # retained batch has both persisted and committed its exact offset.
            now = time.monotonic()
            for key, retry in list(retries.items()):
                if now >= retry.next_retry_at:
                    flush_pending_batch(consumer, pending_batches, retries, key)

            # Liên tục lắng nghe (poll) với timeout 1 giây
            msg = consumer.poll(timeout=1.0)
            
            # Cơ chế "Flush on Idle": Nếu không có message mới nào trong 1 giây, tự động flush batch hiện tại vào DB.
            if msg is None:
                for key in list(pending_batches):
                    if key in retries:
                        continue
                    batch_size = len(pending_batches[key])
                    saved = flush_pending_batch(consumer, pending_batches, retries, key)
                    if saved:
                        print(f"Flushed {batch_size} records to DB due to idle time.")
                continue
                
            # Xử lý lỗi Kafka
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                if msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART or msg.error().retriable():
                    print(
                        f"Kafka topic '{KAFKA_TOPIC}' is temporarily unavailable; "
                        f"retrying in {KAFKA_TOPIC_RETRY_SECONDS}s: {msg.error()}"
                    )
                    time.sleep(KAFKA_TOPIC_RETRY_SECONDS)
                    continue
                raise RuntimeError(f"Kafka consumer error: {msg.error()}")
                    
            try:
                # Đọc payload từ API và parse lại thành Dictionary
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
                
                # Gom đủ một partition batch thì mang đi ghi. A failed batch
                # pauses that partition, so its later offsets cannot overtake it.
                if key not in retries and len(current_batch) >= KAFKA_BATCH_SIZE:
                    batch_size = len(current_batch)
                    saved = flush_pending_batch(consumer, pending_batches, retries, key)
                    if saved:
                        print(f"Completed batch delivery: {batch_size} records to DB.")
                    
            except Exception as parse_e:
                # Never allow a later offset to skip an invalid message. The
                # process exits without committing this position; Compose will
                # restart it and preserve the event for operator remediation.
                raise RuntimeError(f"Error parsing Kafka payload: {parse_e}") from parse_e
                
    except KeyboardInterrupt:
        print("Received shutdown command...")
    finally:
        try:
            if consumer is not None:
                # Try every remaining batch once. Failed batches are intentionally not
                # committed; they will be replayed after the local Compose restart.
                for key in list(pending_batches):
                    flush_pending_batch(consumer, pending_batches, retries, key)
        finally:
            dispatcher_stop.set()
            dispatcher.join(timeout=DISPATCHER_JOIN_TIMEOUT_SECONDS)
            if dispatcher.is_alive():
                print(
                    "Automatic drift outbox dispatcher did not stop before the shutdown timeout; "
                    "leased rows will be retried after their lease expires."
                )
            if consumer is not None:
                consumer.close()
        print("Consumer cleaned up safely.")

if __name__ == '__main__':
    # Đợi Redpanda khởi động hoàn tất trước khi Consumer nhảy vào kết nối
    print("Waiting for Redpanda Broker to start...")
    time.sleep(5)
    main()
