import uuid

from django.db import models


class Build(models.Model):
    STATUSES = tuple(
        (value, value.replace("_", " ").title())
        for value in ("pending", "queued", "building", "ready", "failed", "cancelled")
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="builds")
    source_job = models.ForeignKey(
        "training.TrainingJob",
        on_delete=models.SET_NULL,
        related_name="builds",
        null=True,
        blank=True,
    )
    source_job_reference = models.UUIDField(null=True, blank=True, db_index=True)
    version = models.ForeignKey(
        "registry.ModelVersion", on_delete=models.CASCADE, related_name="builds", null=True, blank=True
    )
    flavor = models.CharField(max_length=80)
    artifact_format = models.CharField(max_length=20, default="raw")
    requirements_snapshot = models.TextField(blank=True)
    backend = models.CharField(max_length=30, default="docker")
    status = models.CharField(max_length=30, choices=STATUSES, default="pending")
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    external_build_id = models.CharField(max_length=255, blank=True)
    image_uri = models.CharField(max_length=1024, blank=True)
    image_digest = models.CharField(max_length=255, blank=True)
    package_uri = models.CharField(max_length=1024, blank=True)
    logs = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "status"], name="build_project_status_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["source_job"],
                condition=models.Q(source_job__isnull=False, status__in=("pending", "queued", "building", "ready")),
                name="build_active_source_job_unique",
            )
        ]

    def __str__(self):
        return f"Build {self.public_id} ({self.status})"


class BuildInputAsset(models.Model):
    KINDS = (
        ("source_artifact", "Source Artifact"),
        ("training_output", "Training Output"),
        ("label_mapping", "Label Mapping"),
        ("metrics", "Metrics"),
        ("params", "Parameters"),
        ("model_insights", "Model Insights"),
        ("feature_importance", "Feature Importance"),
        ("input_schema", "Input Schema"),
    )

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    build = models.ForeignKey(Build, on_delete=models.CASCADE, related_name="input_assets")
    kind = models.CharField(max_length=40, choices=KINDS)
    name = models.CharField(max_length=255)
    s3_uri = models.CharField(max_length=1024, blank=True)
    checksum = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=160, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["build", "kind"], name="build_input_kind_unique")]

    def __str__(self):
        return f"{self.build.public_id}/{self.kind}/{self.name}"


class Deployment(models.Model):
    STATUSES = tuple(
        (value, value.replace("_", " ").title())
        for value in ("pending", "deploying", "healthy", "unhealthy", "failed", "stopped")
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    version = models.ForeignKey("registry.ModelVersion", on_delete=models.PROTECT, related_name="deployments")
    build = models.ForeignKey(Build, on_delete=models.PROTECT, related_name="deployments")
    backend = models.CharField(max_length=30, default="docker")
    status = models.CharField(max_length=30, choices=STATUSES, default="pending")
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    external_deployment_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    deployed_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Deployment {self.public_id} ({self.status})"


class Endpoint(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    deployment = models.OneToOneField(Deployment, on_delete=models.CASCADE, related_name="endpoint")
    public_url = models.CharField(max_length=1024)
    internal_url = models.CharField(max_length=1024, blank=True)
    runtime_name = models.CharField(max_length=255, blank=True)
    runtime_namespace = models.CharField(max_length=255, blank=True)
    health_status = models.CharField(max_length=30, default="unknown")
    last_checked_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.public_url
