from django.db import transaction

from apps.observability.models import EventOutbox


def enqueue_event(*, topic, aggregate_type, aggregate_id, event_type, payload):
    event = EventOutbox.objects.create(
        topic=topic,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
    )
    transaction.on_commit(_publish_pending)
    return event


def _publish_pending():
    from apps.observability.tasks import publish_outbox

    publish_outbox.delay()
