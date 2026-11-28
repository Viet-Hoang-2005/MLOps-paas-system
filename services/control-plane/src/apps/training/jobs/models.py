import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.training.workspace.models import TrainingWorkspace
from common.execution_watch import ExecutionWatch


class TrainingJob(ExecutionWatch):
    artifact_selection = models.JSONField(default=dict, blank=True)
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
    project = models.ForeignKey(
        "catalog.ModelProject", on_delete=models.SET_NULL, related_name="training_jobs", null=True, blank=True
    )
    storage_project_id = models.UUIDField(null=True, blank=True, editable=False)
    storage_layout = models.CharField(
        max_length=16, choices=(("project", "Project"), ("tenant", "Tenant")), default="project"
    )
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_jobs")
    workspace = models.ForeignKey(TrainingWorkspace, on_delete=models.PROTECT, related_name="jobs")
    input_contract = models.CharField(
        max_length=16, default="workspace", choices=(("legacy", "Legacy"), ("workspace", "Workspace"))
    )
    input_revision = models.PositiveIntegerField(null=True, blank=True)
    run_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    submission_token = models.UUIDField(null=True, blank=True, editable=False)
    preparation_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    submitted_at = models.DateTimeField(null=True, blank=True, editable=False)
    environment_snapshot = models.JSONField(default=dict, blank=True)
    secret_snapshot = models.JSONField(default=dict, blank=True, editable=False)
    model_flavor = models.CharField(max_length=40, choices=MODEL_FLAVORS, default="sklearn")
    entry_point = models.CharField(max_length=512, blank=True, default="")
    requirements_text = models.TextField(blank=True)
    build_requirements_text = models.TextField(null=True, blank=True)
    code_snapshot_uri = models.CharField(max_length=1024)
    data_snapshot_uri = models.CharField(max_length=1024)
    output_uri = models.CharField(max_length=1024)
    output_revision = models.PositiveIntegerField(default=1)
    backend = models.CharField(max_length=30, default="local")
    external_job_id = models.CharField(max_length=255, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=30, choices=STATUSES, default="pending")
    vcpu = models.PositiveIntegerField(null=True, blank=True)
    memory_mb = models.PositiveIntegerField(null=True, blank=True)
    max_runtime_seconds = models.PositiveIntegerField(null=True, blank=True)
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
        constraints = [
            models.UniqueConstraint(
                fields=["workspace"],
                condition=models.Q(status__in=["pending", "queued", "running", "uploading", "cancelling"]),
                name="training_workspace_one_active_job",
            )
        ]

    def __str__(self):
        return str(self.public_id)

    def save(self, *args, **kwargs):
        if self.workspace_id and self.owner_id and self.workspace.owner_id != self.owner_id:
            raise ValidationError("Training job and workspace must have the same owner.")
        # Legacy creation paths still supply only project. Keep ownership
        # explicit on the job so it can eventually outlive that relationship.
        if not self.owner_id and self.project_id:
            self.owner_id = self.project.owner_id
        if self.storage_layout == "project" and not self.storage_project_id and self.project_id:
            self.storage_project_id = self.project.public_id
        if self.project_id and self.owner_id != self.project.owner_id:
            raise ValidationError("Training job and project must have the same owner.")
        super().save(*args, **kwargs)

    def mark_started(self):
        if not self.started_at:
            self.started_at = timezone.now()
        self.status = "running"

    @property
    def runtime_project_id(self):
        return str(
            self.storage_project_id
            or (self.project.public_id if self.storage_layout == "project" and self.project_id else "")
        )

    def mark_finished(self, status):
        self.completed_at = timezone.now()
        started = self.runtime_started_at or self.started_at or self.completed_at
        self.runtime_seconds = max(0, int((self.completed_at - started).total_seconds()))
        self.status = status
        if self.pk:
            self.capabilities.filter(purpose="tracking").delete()


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
