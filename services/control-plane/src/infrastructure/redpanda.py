import json

from confluent_kafka import Producer
from django.conf import settings


class RedpandaProducer:
    def __init__(self, producer=None):
        self.producer = producer or Producer({"bootstrap.servers": settings.REDPANDA_BROKERS})

    def publish(self, topic, key, payload):
        self.producer.produce(topic, key=str(key), value=json.dumps(payload))
        remaining = self.producer.flush(10)
        if remaining:
            raise BufferError(f"Redpanda did not flush {remaining} event(s).")
