import uuid

from django.db import models


class EventOutbox(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    topic = models.CharField(max_length=160)
    aggregate_type = models.CharField(max_length=80)
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=120)
    payload = models.JSONField(default=dict)
    headers = models.JSONField(default=dict, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["published_at", "created_at"], name="outbox_pending_idx")]

    def __str__(self):
        return f"{self.event_type} ({self.public_id})"
