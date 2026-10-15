import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    class Type(models.TextChoices):
        TRAINING = "training", "Training"
        BUILD = "build", "Build & Packaging"
        DEPLOYMENT = "deployment", "Deployment"
        DRIFT = "drift", "Data Drift"
        ALERT = "alert", "Model Alert"
        SYSTEM = "system", "System"

    class Level(models.TextChoices):
        INFO = "info", "Information"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    tenant_id = models.CharField(max_length=64, blank=True, db_index=True)
    
    type = models.CharField(max_length=32, choices=Type.choices, default=Type.SYSTEM, db_index=True)
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.INFO)
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    link = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
            models.Index(fields=["user", "type", "-created_at"]),
        ]

    def __str__(self):
        return f"[{self.level.upper()}] {self.title} ({self.user})"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])
