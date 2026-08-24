import uuid

from django.db import models
from django.utils import timezone


class TrainingJob(models.Model):
    MODEL_FLAVORS = (
        ("sklearn", "Scikit-learn"),
        ("xgboost", "XGBoost"),
        ("pytorch", "PyTorch"),
        ("tensorflow", "TensorFlow"),
    )
    STATUSES = tuple(
        (value, value.replace("_", " ").title())
        for value in (
            "pending",
            "queued",
            "uploading",
            "running",
            "cancelling",
            "completed",
            "failed",
            "cancelled",
        )
    )
    ACCELERATORS = (("none", "None"), ("gpu", "GPU"))

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="training_jobs")
    retry_of = models.ForeignKey("self", on_delete=models.SET_NULL, related_name="retries", null=True, blank=True)
    name = models.CharField(max_length=160)
    model_flavor = models.CharField(max_length=40, choices=MODEL_FLAVORS)
    entry_point = models.CharField(max_length=512, default="train.py")
    requirements_text = models.TextField(blank=True)
    code_snapshot_uri = models.CharField(max_length=1024)
    data_snapshot_uri = models.CharField(max_length=1024)
    output_uri = models.CharField(max_length=1024)
    mlflow_artifact_uri = models.CharField(max_length=1024, blank=True)
    mlflow_run_id = models.CharField(max_length=255, blank=True, db_index=True)
    backend = models.CharField(max_length=30, default="local")
    external_job_id = models.CharField(max_length=255, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=30, choices=STATUSES, default="pending")
    vcpu = models.PositiveIntegerField(default=2)
    memory_mb = models.PositiveIntegerField(default=4096)
    max_runtime_seconds = models.PositiveIntegerField(default=3600)
    accelerator_type = models.CharField(max_length=20, choices=ACCELERATORS, default="none")
    accelerator_count = models.PositiveIntegerField(default=0)
    tracking = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    runtime_seconds = models.PositiveIntegerField(default=0)
    outputs_purged_at = models.DateTimeField(null=True, blank=True)
    deletion_requested_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deletion_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "status"], name="training_project_status_idx")]

    def __str__(self):
        return f"{self.name} ({self.public_id})"

    def mark_started(self):
        if not self.started_at:
            self.started_at = timezone.now()
        self.status = "running"

    def mark_finished(self, status):
        self.completed_at = timezone.now()
        started = self.started_at or self.created_at or self.completed_at
        self.runtime_seconds = max(0, int((self.completed_at - started).total_seconds()))
        self.status = status


class TrainingJobEvent(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    job = models.ForeignKey(TrainingJob, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=40)
    message = models.CharField(max_length=1000)
    metadata = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="training_event_idempotency_unique",
            )
        ]

    def __str__(self):
        return f"{self.job.public_id}: {self.event_type}"


class TrainingJobCapability(models.Model):
    PURPOSES = (
        ("output_upload", "Output upload"),
        ("trusted_reporter", "Trusted reporter"),
        ("cancel_reporter", "Cancellation reporter"),
    )

    job = models.ForeignKey(TrainingJob, on_delete=models.CASCADE, related_name="capabilities")
    purpose = models.CharField(max_length=40, choices=PURPOSES)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["job", "purpose", "expires_at"], name="training_capability_idx")]

    def __str__(self):
        return f"{self.job.public_id}/{self.purpose}"


class TrainingOutput(models.Model):
    KINDS = (("model", "Model"), ("metric", "Metric"), ("insight", "Insight"), ("file", "File"))
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
        constraints = [models.UniqueConstraint(fields=["job", "relative_path"], name="training_output_path_unique")]

    def __str__(self):
        return f"{self.job.public_id}/{self.relative_path}"
