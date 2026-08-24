import uuid

from django.db import models


class DriftMonitor(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    version = models.ForeignKey("registry.ModelVersion", on_delete=models.CASCADE, related_name="drift_monitors")
    reference_asset = models.ForeignKey(
        "catalog.WorkspaceAsset", on_delete=models.PROTECT, related_name="drift_monitors"
    )
    name = models.CharField(max_length=160)
    trigger_threshold = models.PositiveIntegerField(default=1000)
    last_automatic_trigger_count = models.PositiveBigIntegerField(default=0)
    backend = models.CharField(max_length=30, default="docker")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "name"], name="drift_version_name_unique")]

    def __str__(self):
        return f"{self.version}: {self.name}"


class DriftRun(models.Model):
    STATUSES = tuple(
        (value, value.title()) for value in ("pending", "queued", "running", "completed", "failed", "cancelled")
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    monitor = models.ForeignKey(DriftMonitor, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=30, choices=STATUSES, default="pending")
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    external_run_id = models.CharField(max_length=255, blank=True)
    current_data_uri = models.CharField(max_length=1024, blank=True)
    report_html_uri = models.CharField(max_length=1024, blank=True)
    report_json_uri = models.CharField(max_length=1024, blank=True)
    summary_uri = models.CharField(max_length=1024, blank=True)
    drift_score = models.FloatField(null=True, blank=True)
    has_drift = models.BooleanField(null=True)
    summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Drift run {self.public_id} ({self.status})"
