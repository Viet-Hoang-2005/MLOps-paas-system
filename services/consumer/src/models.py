"""Domain records used by the Kafka consumer."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KafkaRecord:
    payload: dict[str, Any]
    topic: str
    partition: int
    offset: int


@dataclass
class RetryState:
    attempts: int = 0
    next_retry_at: float = 0.0


class KafkaRecordProcessingError(RuntimeError):
    """Safe terminal error that never retains the untrusted record payload."""

    def __init__(self, error_type: str):
        super().__init__("Kafka record processing failed")
        self.error_type = error_type
