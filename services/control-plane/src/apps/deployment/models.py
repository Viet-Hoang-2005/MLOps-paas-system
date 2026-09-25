import uuid

from django.db import models


class Build(models.Model):
    STATUSES = tuple(
        (value, value.replace("_", " ").title())
        for value in ("pending", "queued", "building", "ready", "failed", "cancelled")
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="builds")
    source_draft_revision = models.ForeignKey(
        "catalog.ModelDraftRevision", on_delete=models.PROTECT, related_name="builds", null=True, blank=True
    )
    source_version = models.ForeignKey(
        "registry.ModelVersion",
        on_delete=models.SET_NULL,
        related_name="derived_builds",
        null=True,
        blank=True,
    )
    source_job = models.ForeignKey(
        "training.TrainingJob",
        on_delete=models.SET_NULL,
        related_name="builds",
        null=True,
        blank=True,
    )
    source_job_reference = models.UUIDField(null=True, blank=True, db_index=True)
    version = models.ForeignKey(
        "registry.ModelVersion", on_delete=models.SET_NULL, related_name="builds", null=True, blank=True
    )
    flavor = models.CharField(max_length=80)
    artifact_format = models.CharField(max_length=20, default="raw")
    requirements_snapshot = models.TextField(blank=True)
    metrics_summary = models.JSONField(default=dict, blank=True)
    params_summary = models.JSONField(default=dict, blank=True)
    insights_summary = models.JSONField(default=dict, blank=True)
    backend = models.CharField(max_length=30, default="docker")
    status = models.CharField(max_length=30, choices=STATUSES, default="pending")
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    external_build_id = models.CharField(max_length=255, blank=True)
    image_uri = models.CharField(max_length=1024, blank=True)
    image_digest = models.CharField(max_length=255, blank=True)
    package_uri = models.CharField(max_length=1024, blank=True)
    log_uri = models.CharField(max_length=1024, blank=True)
    log_tail = models.TextField(blank=True)
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
            models.CheckConstraint(
                check=(
                    models.Q(source_draft_revision__isnull=False, source_version__isnull=True, source_job__isnull=True, source_job_reference__isnull=True)
                    | models.Q(source_draft_revision__isnull=True, source_version__isnull=False, source_job__isnull=True, source_job_reference__isnull=True)
                    | models.Q(source_draft_revision__isnull=True, source_version__isnull=True, source_job_reference__isnull=False)
                ),
                name="build_exactly_one_source",
            ),
            models.UniqueConstraint(
                fields=["source_job"],
                condition=models.Q(source_job__isnull=False, status__in=("pending", "queued", "building", "ready")),
                name="build_active_source_job_unique",
            )
        ]

    @property
    def source_kind(self):
        if self.source_draft_revision_id:
            return "draft"
        if self.source_version_id:
            return "model_version"
        if self.source_job_id or self.source_job_reference:
            return "training_job"
        return None

    def save(self, *args, **kwargs):
        if self.source_job_id and not self.source_job_reference:
            self.source_job_reference = self.source_job.public_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Build {self.public_id} ({self.status})"


class BuildInputAsset(models.Model):
    KINDS = (
        ("model", "Model Artifact"),
        ("reference_data", "Reference Data"),
        ("source_code", "Source Code"),
        ("label_mapping", "Label Mapping"),
        ("data_contract", "Data Contract"),
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
    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="deployments")
    version = models.ForeignKey("registry.ModelVersion", on_delete=models.PROTECT, related_name="deployments")
    build = models.ForeignKey(Build, on_delete=models.PROTECT, related_name="deployments", null=True, blank=True)
    target = models.CharField(max_length=20, choices=(("staging", "Staging"), ("production", "Production")))
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
        constraints = [
            models.UniqueConstraint(
                fields=["project", "target"],
                condition=models.Q(status__in=("pending", "deploying", "healthy")),
                name="deployment_active_target_project_unique",
            )
        ]

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
