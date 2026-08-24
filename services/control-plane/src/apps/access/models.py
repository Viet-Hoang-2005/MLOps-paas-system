import hashlib
import secrets
import uuid

from django.conf import settings
from django.db import models


class UserAPIKey(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    key_prefix = models.CharField(max_length=24, db_index=True)
    key_hash = models.CharField(max_length=64)
    allowed_projects = models.ManyToManyField("catalog.ModelProject", related_name="api_keys", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="api_key_user_name_unique")]

    def __str__(self):
        return f"{self.name} ({self.key_prefix})"

    @staticmethod
    def issue():
        raw_key = f"mlp_{secrets.token_urlsafe(32)}"
        return raw_key, raw_key[:16], hashlib.sha256(raw_key.encode()).hexdigest()

    def matches(self, raw_key):
        return secrets.compare_digest(self.key_hash, hashlib.sha256(raw_key.encode()).hexdigest())
