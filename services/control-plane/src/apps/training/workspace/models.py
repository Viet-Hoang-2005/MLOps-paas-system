import uuid

from django.conf import settings
from django.db import models

from apps.training.resources.models import LocalTrainingReservation, TrainingQuotaReservation


class TrainingWorkspace(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_workspaces")
    revision = models.PositiveIntegerField(default=1)
    entry_point = models.CharField(max_length=512, blank=True, default="")
    environment = models.JSONField(default=dict, blank=True)
    model_flavor = models.CharField(max_length=40, default="sklearn")
    vcpu = models.PositiveIntegerField(null=True, blank=True)
    memory_mb = models.PositiveIntegerField(null=True, blank=True)
    max_runtime_seconds = models.PositiveIntegerField(null=True, blank=True)
    accelerator_type = models.CharField(max_length=20, default="none")
    accelerator_count = models.PositiveIntegerField(default=0)
    accelerator_model = models.CharField(max_length=16, blank=True, default="")
    local_gpu_id = models.CharField(max_length=80, blank=True, default="")
    deletion_requested_at = models.DateTimeField(null=True, blank=True)
    deletion_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return str(self.public_id)

    @staticmethod
    def active_filter():
        return (
            models.Q(status__in=["pending", "queued", "running", "uploading", "cancelling"])
            | models.Q(observation_status="cleanup_pending")
            | models.Q(public_id__in=LocalTrainingReservation.objects.filter(active=True).values("job_id"))
            | models.Q(public_id__in=TrainingQuotaReservation.objects.filter(active=True).values("job_id"))
        )

    def active_jobs(self):
        return self.jobs.filter(self.active_filter())

    @property
    def status(self):
        if self.deletion_requested_at:
            return "delete_failed" if self.deletion_error else "deleting"
        prefetched = getattr(self, "_display_active_jobs", None)
        job = (prefetched[0] if prefetched else None) if prefetched is not None else self.active_jobs().first()
        if not job:
            return "ready"
        return "preparing" if job.status == "pending" and not job.submitted_at else "running"


class TrainingWorkspaceEntry(models.Model):
    KINDS = (
        ("folder", "Folder"),
        ("script", "Script"),
        ("data", "Data"),
        ("config", "Config"),
        ("document", "Document"),
        ("requirements", "Requirements"),
    )

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
        constraints = [
            models.UniqueConstraint(fields=["workspace", "relative_path"], name="training_workspace_entry_path_unique")
        ]

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
