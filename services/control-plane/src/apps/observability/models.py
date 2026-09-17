import uuid

from django.db import models


def new_idempotency_key():
    return str(uuid.uuid4())


class EventOutbox(models.Model):
    DELIVERY_KINDS = (("kafka", "Kafka"), ("webhook", "Webhook"))

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    idempotency_key = models.CharField(max_length=255, unique=True, default=new_idempotency_key)
    delivery_kind = models.CharField(max_length=16, choices=DELIVERY_KINDS)
    destination = models.CharField(max_length=255)
    aggregate_type = models.CharField(max_length=80)
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=120)
    payload = models.JSONField(default=dict)
    headers = models.JSONField(default=dict, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(auto_now_add=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["delivery_kind", "published_at", "available_at"], name="outbox_delivery_ready_idx"),
            models.Index(fields=["locked_until"], name="outbox_lease_idx"),
        ]

    def __str__(self):
        return f"{self.delivery_kind}:{self.event_type} ({self.public_id})"


class LifecycleEvent(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey("catalog.ModelProject", on_delete=models.SET_NULL, null=True, blank=True, related_name="lifecycle_events")
    aggregate_type = models.CharField(max_length=80)
    aggregate_id = models.UUIDField()
    actor = models.ForeignKey("identity.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="lifecycle_events")
    event_type = models.CharField(max_length=60)
    from_state = models.CharField(max_length=80, blank=True)
    to_state = models.CharField(max_length=80, blank=True)
    message = models.CharField(max_length=1000, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True)
    correlation_id = models.UUIDField(null=True, blank=True)
    maintenance_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["aggregate_type", "aggregate_id", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="lifecycle_event_idempotency_unique",
            )
        ]
        indexes = [
            models.Index(fields=["project", "created_at"], name="lifecycle_project_created_idx"),
            models.Index(fields=["aggregate_type", "aggregate_id", "created_at"], name="life_aggregate_created_idx"),
        ]
