import uuid

from django.conf import settings
from django.core.exceptions import ValidationError

from django.db import models
from django.utils import timezone
from common.execution_watch import ExecutionWatch


class TrainingWorkspace(models.Model):
    """An account-owned editable draft, independent of a model project."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_workspaces")
    entry_point = models.CharField(max_length=512, blank=True)
    environment = models.JSONField(default=dict, blank=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.public_id)


class TrainingWorkspaceEntry(models.Model):
    KINDS = (("folder", "Folder"), ("script", "Script"), ("data", "Data"),
             ("config", "Config"), ("document", "Document"), ("requirements", "Requirements"))

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    workspace = models.ForeignKey(TrainingWorkspace, on_delete=models.CASCADE, related_name="entries")
    relative_path = models.CharField(max_length=512)
    kind = models.CharField(max_length=16, choices=KINDS)
    s3_uri = models.CharField(max_length=1024, blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "relative_path"], name="training_workspace_entry_path_unique")]

    def __str__(self):
        return f"{self.workspace_id}/{self.relative_path}"


class TrainingWorkspaceSecret(models.Model):
    workspace = models.ForeignKey(TrainingWorkspace, on_delete=models.CASCADE, related_name="secrets")
    name = models.CharField(max_length=128)
    ciphertext = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="training_workspace_secret_unique")]

    def __str__(self):
        return f"{self.workspace_id}/{self.name}"


class TrainingJob(ExecutionWatch):
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
    project = models.ForeignKey("catalog.ModelProject", on_delete=models.SET_NULL, related_name="training_jobs", null=True, blank=True)
    storage_project_id = models.UUIDField(null=True, blank=True, editable=False)
    storage_layout = models.CharField(max_length=16, choices=(("project", "Project"), ("tenant", "Tenant")), default="project")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_jobs")
    workspace = models.ForeignKey(
        TrainingWorkspace, on_delete=models.SET_NULL, related_name="jobs", null=True, blank=True
    )
    input_contract = models.CharField(max_length=16, default="legacy", choices=(("legacy", "Legacy"), ("workspace", "Workspace")))
    workspace_revision = models.PositiveIntegerField(null=True, blank=True)
    run_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    environment_snapshot = models.JSONField(default=dict, blank=True)
    secret_snapshot = models.JSONField(default=dict, blank=True, editable=False)
    retry_of = models.ForeignKey("self", on_delete=models.SET_NULL, related_name="retries", null=True, blank=True)
    trigger_kind = models.CharField(
        max_length=32,
        choices=(("manual", "Manual"), ("retry", "Retry"), ("maintenance", "Maintenance")),
        default="manual",
    )
    baseline_version = models.ForeignKey(
        "registry.ModelVersion", on_delete=models.SET_NULL, related_name="baseline_training_jobs", null=True, blank=True
    )
    dataset_snapshot = models.ForeignKey(
        "ct.DatasetSnapshot", on_delete=models.SET_NULL, related_name="training_jobs", null=True, blank=True
    )
    recipe_version = models.CharField(max_length=80, blank=True)
    model_flavor = models.CharField(max_length=40, choices=MODEL_FLAVORS)
    entry_point = models.CharField(max_length=512, default="train.py")
    requirements_text = models.TextField(blank=True)
    build_requirements_text = models.TextField(null=True, blank=True)
    code_snapshot_uri = models.CharField(max_length=1024)
    data_snapshot_uri = models.CharField(max_length=1024)
    output_uri = models.CharField(max_length=1024)
    output_revision = models.PositiveIntegerField(default=1)
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
    accelerator_model = models.CharField(max_length=16, blank=True, default="")
    local_gpu_id = models.CharField(max_length=80, blank=True, default="")
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
        return str(self.public_id)

    def save(self, *args, **kwargs):
        # Legacy creation paths still supply only project. Keep ownership
        # explicit on the job so it can eventually outlive that relationship.
        if not self.owner_id and self.project_id:
            self.owner_id = self.project.owner_id
        if self.storage_layout == "project" and not self.storage_project_id and self.project_id:
            self.storage_project_id = self.project.public_id
        if self.project_id and self.owner_id != self.project.owner_id:
            raise ValidationError("Training job and project must have the same owner.")
        if self.workspace_id and self.owner_id != self.workspace.owner_id:
            raise ValidationError("Training job and workspace must have the same owner.")
        super().save(*args, **kwargs)

    def mark_started(self):
        if not self.started_at:
            self.started_at = timezone.now()
        self.status = "running"

    @property
    def runtime_project_id(self):
        return str(self.storage_project_id or (self.project.public_id if self.storage_layout == "project" and self.project_id else ""))

    def mark_finished(self, status):
        self.completed_at = timezone.now()
        started = self.runtime_started_at or self.started_at or self.created_at or self.completed_at
        self.runtime_seconds = max(0, int((self.completed_at - started).total_seconds()))
        self.status = status
        if self.pk:
            self.capabilities.filter(purpose="tracking").delete()


class LocalTrainingPool(models.Model):
    daemon_id = models.CharField(max_length=128, unique=True)

    def __str__(self):
        return self.daemon_id


class LocalTrainingReservation(models.Model):
    pool = models.ForeignKey(LocalTrainingPool, on_delete=models.PROTECT, related_name="reservations")
    job_id = models.UUIDField(unique=True)
    vcpu = models.PositiveIntegerField()
    memory_mb = models.PositiveIntegerField()
    active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return str(self.job_id)


class TrainingQuotaReservation(models.Model):
    """Durable usage survives deletion of the job and its project."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_quota_reservations")
    job_id = models.UUIDField(unique=True)
    resource = models.CharField(max_length=16)
    submitted_at = models.DateTimeField()
    dispatch_deadline_at = models.DateTimeField()
    max_runtime_seconds = models.PositiveIntegerField()
    started_at = models.DateTimeField(null=True, blank=True)
    runtime_finished_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return f"{self.job_id}:{self.resource}"


class TrainingQuotaWeek(models.Model):
    reservation = models.ForeignKey(TrainingQuotaReservation, on_delete=models.CASCADE, related_name="weeks")
    week_start = models.DateTimeField()
    reserved_seconds = models.PositiveIntegerField(default=0)
    used_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["reservation", "week_start"], name="training_quota_job_week_unique")]
        indexes = [models.Index(fields=["week_start"], name="training_quota_week_idx")]

    def __str__(self):
        return f"{self.reservation_id}:{self.week_start}"


class TrainingJobCapability(models.Model):
    PURPOSES = (
        ("input_download", "Input download"),
        ("output_upload", "Output upload"),
        ("trusted_reporter", "Trusted reporter"),
        ("cancel_reporter", "Cancellation reporter"),
        ("tracking", "Tracking reporter"),
        ("runtime_config", "Runtime configuration"),
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


class TrainingJobMetric(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    job = models.ForeignKey(TrainingJob, on_delete=models.CASCADE, related_name="step_metrics")
    name = models.CharField(max_length=160, db_index=True)
    value = models.FloatField()
    step = models.IntegerField(default=0, db_index=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["job", "name", "step"], name="train_metric_job_step_idx"),
            models.Index(fields=["job", "created_at"], name="train_metric_job_created_idx"),
        ]

    def __str__(self):
        return f"{self.job.public_id}:{self.name}[{self.step}]={self.value}"


class TrainingJobParam(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    job = models.ForeignKey(TrainingJob, on_delete=models.CASCADE, related_name="hyperparameters")
    name = models.CharField(max_length=160)
    value = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "name"], name="training_job_param_unique"),
        ]

    def __str__(self):
        return f"{self.job.public_id}:{self.name}={self.value}"


class TrainingJobTag(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    job = models.ForeignKey(TrainingJob, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=160)
    value = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "name"], name="training_job_tag_unique"),
        ]

    def __str__(self):
        return f"{self.job.public_id}:{self.name}"


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


class TrainingStorageCopy(models.Model):
    job = models.ForeignKey(TrainingJob, on_delete=models.CASCADE, related_name="storage_copies")
    source_uri = models.CharField(max_length=1024)
    destination_uri = models.CharField(max_length=1024)
    source_etag = models.CharField(max_length=160)
    checksum = models.CharField(max_length=64)
    verified_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["job", "source_uri"], name="training_storage_copy_unique")]

    def __str__(self):
        return f"{self.job_id}: {self.source_uri}"

