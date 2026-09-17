import uuid

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.catalog.models import ModelProject
from apps.observability.models import EventOutbox
from apps.observability.services.outbox import claim_events, enqueue_event


@pytest.mark.django_db
def test_kafka_claim_does_not_claim_webhook_rows():
    owner = get_user_model().objects.create_user("outbox@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="Outbox")
    enqueue_event(
        topic="registry.events", aggregate_type="model_project", aggregate_id=project.public_id,
        event_type="model.promoted", payload={"project_id": str(project.public_id)},
    )
    EventOutbox.objects.create(
        delivery_kind="webhook", destination="automatic_drift", aggregate_type="model_version",
        aggregate_id=uuid.uuid4(), event_type="automatic_drift.requested",
        payload={}, idempotency_key="webhook-event", available_at=timezone.now(),
    )

    claimed = claim_events(delivery_kind="kafka")

    assert len(claimed) == 1
    assert claimed[0].delivery_kind == "kafka"
    assert EventOutbox.objects.get(idempotency_key="webhook-event").locked_until is None
