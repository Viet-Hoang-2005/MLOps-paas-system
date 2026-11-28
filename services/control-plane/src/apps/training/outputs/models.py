import uuid

from django.db import models

from apps.training.jobs.models import TrainingJob


class TrainingOutput(models.Model):
    KINDS = (
        ("model", "Model"),
        ("metric", "Metric"),
        ("insight", "Insight"),
        ("source_code", "Source Code"),
        ("reference_data", "Reference Data"),
        ("file", "File"),
        ("label_mapping", "Label mapping"),
        ("input_schema", "Input schema"),
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    job = models.ForeignKey(TrainingJob, on_delete=models.CASCADE, related_name="outputs")
    kind = models.CharField(max_length=30, choices=KINDS, default="file")
    relative_path = models.CharField(max_length=512)
    s3_uri = models.CharField(max_length=1024)
    checksum = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=160, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "relative_path"], name="training_output_path_unique"),
            models.UniqueConstraint(
                fields=["job", "kind"],
                condition=models.Q(kind__in=["source_code", "reference_data"]),
                name="training_output_unique_supplemental_kind",
            ),
        ]

    def __str__(self):
        return f"{self.job.public_id}/{self.relative_path}"
