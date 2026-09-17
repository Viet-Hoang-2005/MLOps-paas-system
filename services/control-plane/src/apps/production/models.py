import uuid

from django.db import models


class PredictionRecord(models.Model):
    """A validated, replay-safe inference result retained for monitoring and CT."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="prediction_records")
    model_version = models.ForeignKey("registry.ModelVersion", on_delete=models.CASCADE, related_name="prediction_records")
    observed_at = models.DateTimeField()
    features = models.JSONField(default=dict)
    prediction = models.TextField(blank=True)
    # Existing producers emit confidence as a percentage.  Keep that contract.
    confidence = models.FloatField(null=True, blank=True)
    positive_class_probability = models.FloatField(null=True, blank=True)
    class_mapping = models.JSONField(default=dict, blank=True)
    decision_threshold = models.FloatField(null=True, blank=True)
    calibration_version = models.CharField(max_length=80, blank=True)
    latency_ms = models.FloatField(null=True, blank=True)
    request_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-observed_at", "-id"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(positive_class_probability__isnull=True)
                | (models.Q(positive_class_probability__gte=0) & models.Q(positive_class_probability__lte=1)),
                name="production_probability_range",
            ),
            models.CheckConstraint(
                check=models.Q(decision_threshold__isnull=True)
                | (models.Q(decision_threshold__gte=0) & models.Q(decision_threshold__lte=1)),
                name="production_threshold_range",
            ),
            models.CheckConstraint(
                check=models.Q(latency_ms__isnull=True) | models.Q(latency_ms__gte=0),
                name="production_latency_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["model_version", "-observed_at"], name="prod_version_observed_idx"),
            models.Index(fields=["project", "-observed_at"], name="prod_project_observed_idx"),
        ]
