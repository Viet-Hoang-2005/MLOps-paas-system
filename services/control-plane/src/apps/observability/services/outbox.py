from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.observability.models import EventOutbox


def enqueue_event(*, topic, aggregate_type, aggregate_id, event_type, payload, idempotency_key=None):
    event = EventOutbox.objects.create(
        idempotency_key=idempotency_key or EventOutbox._meta.get_field("idempotency_key").get_default(),
        delivery_kind="kafka",
        destination=topic,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
    )
    transaction.on_commit(_publish_pending)
    return event


def claim_events(*, delivery_kind, limit=100, lease_seconds=60, destination=None):
    """Lease ready rows atomically; workers must finish or reschedule each row."""
    now = timezone.now()
    ready = Q(available_at__lte=now) & (Q(locked_until__isnull=True) | Q(locked_until__lte=now))
    with transaction.atomic():
        queryset = EventOutbox.objects.select_for_update(skip_locked=True).filter(
            delivery_kind=delivery_kind, published_at__isnull=True
        ).filter(ready)
        if destination:
            queryset = queryset.filter(destination=destination)
        events = list(queryset.order_by("available_at", "created_at")[:limit])
        for event in events:
            event.attempts += 1
            event.locked_until = now + timedelta(seconds=lease_seconds)
            event.save(update_fields=["attempts", "locked_until"])
    return events


def mark_published(event):
    EventOutbox.objects.filter(pk=event.pk).update(published_at=timezone.now(), locked_until=None, last_error="")


def reschedule(event, error, delay_seconds):
    EventOutbox.objects.filter(pk=event.pk).update(
        available_at=timezone.now() + timedelta(seconds=delay_seconds), locked_until=None, last_error=error[:4000]
    )


def _publish_pending():
    from apps.observability.tasks import publish_outbox

    publish_outbox.delay()
