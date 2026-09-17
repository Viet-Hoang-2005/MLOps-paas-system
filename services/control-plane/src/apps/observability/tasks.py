from celery import shared_task
from infrastructure.redpanda import RedpandaProducer


@shared_task(bind=True, autoretry_for=(BufferError,), retry_backoff=True, max_retries=8)
def publish_outbox(self, limit=100):
    from .services.outbox import claim_events, mark_published, reschedule

    producer = RedpandaProducer()
    published = 0
    for event in claim_events(delivery_kind="kafka", limit=limit):
        try:
            producer.publish(event.destination, event.aggregate_id, event.payload)
        except BufferError:
            reschedule(event, "Kafka producer buffer is full", min(300, 5 * (2 ** max(0, event.attempts - 1))))
            raise
        except Exception as exc:
            reschedule(event, type(exc).__name__, min(300, 5 * (2 ** max(0, event.attempts - 1))))
            continue
        mark_published(event)
        published += 1
    return published
