from celery import shared_task
from django.utils import timezone
from infrastructure.redpanda import RedpandaProducer


@shared_task(bind=True, autoretry_for=(BufferError,), retry_backoff=True, max_retries=8)
def publish_outbox(self, limit=100):
    from .selectors import pending_outbox_events

    producer = RedpandaProducer()
    published = 0
    for event in pending_outbox_events(limit):
        producer.publish(event.topic, event.aggregate_id, event.payload)
        event.published_at = timezone.now()
        event.attempts += 1
        event.save(update_fields=["published_at", "attempts"])
        published += 1
    return published
