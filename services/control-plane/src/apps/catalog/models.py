import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ModelProject(models.Model):
    ACCESS_MODES = (("private", "Private"), ("public", "Public"))
    DELETION_STATES = (
        ("active", "Active"),
        ("deleting", "Deleting"),
        ("deleted", "Deleted"),
        ("delete_failed", "Delete Failed"),
    )

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="model_projects")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    access_mode = models.CharField(max_length=20, choices=ACCESS_MODES, default="private")
    next_version_number = models.PositiveIntegerField(default=1)
    active_deployment = models.ForeignKey(
        "deployment.Deployment", on_delete=models.SET_NULL, null=True, blank=True, related_name="active_projects"
    )
    is_active = models.BooleanField(default=True)
    deletion_state = models.CharField(max_length=20, choices=DELETION_STATES, default="active")
    deletion_error = models.TextField(blank=True)
    deletion_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        # Cleanup can be retried while inactive; finalization removes the row.
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"], condition=Q(is_active=True), name="project_owner_active_name_unique"
            )
        ]
        indexes = [models.Index(fields=["owner", "is_active"], name="project_owner_active_idx")]

    def __str__(self):
        return f"{self.name} ({self.public_id})"


class WorkspaceAsset(models.Model):
    KINDS = (("code", "Code"), ("data", "Data"))

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(ModelProject, on_delete=models.CASCADE, related_name="workspace_assets")
    kind = models.CharField(max_length=20, choices=KINDS)
    relative_path = models.CharField(max_length=512)
    s3_uri = models.CharField(max_length=1024)
    checksum = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "relative_path"]
        constraints = [
            models.UniqueConstraint(fields=["project", "kind", "relative_path"], name="workspace_asset_path_unique")
        ]

    def __str__(self):
        return f"{self.project.name}/{self.kind}/{self.relative_path}"


class ModelPreview(models.Model):
    """The single editable input draft; builds and versions never read it after snapshotting."""

    project = models.OneToOneField(ModelProject, on_delete=models.CASCADE, related_name="preview")
    flavor = models.CharField(max_length=80, blank=True)
    artifact_format = models.CharField(max_length=20, default="raw")
    requirements_text = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preview {self.project.public_id} r{self.revision}"


class PreviewAsset(models.Model):
    KINDS = tuple(
        (kind, kind.replace("_", " ").title())
        for kind in (
            "source_artifact",
            "source_code",
            "reference_data",
            "label_mapping",
            "metrics",
            "params",
            "model_insights",
            "feature_importance",
            "input_schema",
        )
    )
    preview = models.ForeignKey(ModelPreview, on_delete=models.CASCADE, related_name="assets")
    kind = models.CharField(max_length=40, choices=KINDS)
    name = models.CharField(max_length=255)
    s3_uri = models.CharField(max_length=1024)
    checksum = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=160, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["preview", "kind"], name="preview_asset_kind_unique")]

    def __str__(self):
        return f"{self.preview_id}/{self.kind}"
