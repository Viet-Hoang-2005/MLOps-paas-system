"""Dead-letter topic for records the consumer cannot persist."""

from dataclasses import dataclass

from confluent_kafka import Producer

from src.logging_utils import get_logger, log_event

logger = get_logger(__name__)


@dataclass(frozen=True)
class DeadLetter:
    value: bytes
    topic: str
    partition: int
    offset: int
    reason: str


class DeadLetterQueue:
    """Publish records to a Kafka topic so they can be inspected and replayed.

    ``publish`` reports success only when the broker acknowledged every record,
    so callers drop a record from the main flow only after it is safely parked.
    """

    def __init__(self, brokers: str, topic: str, flush_timeout: float = 5.0, producer_factory=Producer):
        self.topic = topic.strip()
        self._brokers = brokers
        self._flush_timeout = flush_timeout
        self._producer_factory = producer_factory
        self._producer = None

    @property
    def enabled(self) -> bool:
        return bool(self.topic)

    def _get_producer(self):
        if self._producer is None:
            self._producer = self._producer_factory({"bootstrap.servers": self._brokers, "acks": "all"})
        return self._producer

    def publish(self, letters: list[DeadLetter]) -> bool:
        if not self.enabled:
            return False
        failures: list[str] = []

        def on_delivery(error, _message):
            if error is not None:
                failures.append(str(error.code()) if hasattr(error, "code") else "delivery_error")

        try:
            producer = self._get_producer()
            for letter in letters:
                producer.produce(
                    self.topic,
                    value=letter.value,
                    # Stable key: replaying the same record never creates a distinct identity.
                    key=f"{letter.topic}:{letter.partition}:{letter.offset}".encode(),
                    headers=[
                        ("x-source-topic", letter.topic.encode()),
                        ("x-source-partition", str(letter.partition).encode()),
                        ("x-source-offset", str(letter.offset).encode()),
                        ("x-failure-reason", letter.reason.encode()),
                    ],
                    on_delivery=on_delivery,
                )
            remaining = producer.flush(self._flush_timeout)
        except Exception as exc:
            log_event(
                logger,
                "ERROR",
                "dead_letter_publish_failed",
                "Dead-letter publish raised an error",
                error_type=type(exc).__name__,
                count=len(letters),
            )
            return False
        if remaining or failures:
            log_event(
                logger,
                "ERROR",
                "dead_letter_publish_failed",
                "Dead-letter records were not acknowledged by the broker",
                undelivered=remaining + len(failures),
                count=len(letters),
            )
            return False
        return True
