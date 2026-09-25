import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ModelProject(models.Model):
    ACCESS_MODES = (("private", "Private"), ("public", "Public"))
    TASK_DOMAINS = (
        ("binary_classification", "Binary Classification"),
        ("multiclass_classification", "Multiclass Classification"),
        ("regression", "Regression"),
        ("ranking", "Ranking"),
        ("general", "General"),
    )
    LIFECYCLE_STATUSES = (
        ("active", "Active"),
        ("archived", "Archived"),
        ("deleted", "Deleted"),
    )
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
    task_domain = models.CharField(max_length=64, choices=TASK_DOMAINS, default="binary_classification")
    lifecycle_status = models.CharField(max_length=20, choices=LIFECYCLE_STATUSES, default="active")
    next_version_number = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    deletion_state = models.CharField(max_length=20, choices=DELETION_STATES, default="active")
    deletion_error = models.TextField(blank=True)
    deletion_task_id = models.CharField(max_length=255, blank=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="project_owner_name_unique")]
        indexes = [models.Index(fields=["owner", "is_active"], name="project_owner_active_idx")]

    def __str__(self):
        return f"{self.name} ({self.public_id})"

    @property
    def current_draft(self):
        draft, _ = ModelDraft.objects.get_or_create(project=self)
        return draft


class ModelDraft(models.Model):
    STATUS_CHOICES = (
        ("editing", "Editing"),
        ("saving", "Saving"),
        ("ready", "Ready"),
        ("locked", "Locked"),
    )
    FORMAT_CHOICES = (
        ("raw", "Raw"),
        ("archive", "Archive"),
    )

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.OneToOneField(ModelProject, on_delete=models.CASCADE, related_name="draft")
    flavor = models.CharField(max_length=80, blank=True)
    artifact_format = models.CharField(max_length=20, choices=FORMAT_CHOICES, default="raw")
    requirements_snapshot = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)
    saved_revision = models.PositiveIntegerField(default=0)
    saved_snapshot = models.ForeignKey(
        "catalog.ModelDraftRevision", on_delete=models.SET_NULL, null=True, blank=True, related_name="current_drafts"
    )
    source_version = models.ForeignKey(
        "registry.ModelVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="loaded_drafts"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="editing")
    locked_by_build = models.ForeignKey(
        "deployment.Build",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_drafts",
    )
    saved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Draft for {self.project.name} (r{self.revision})"

    @property
    def is_dirty(self) -> bool:
        return self.revision != self.saved_revision

    def has_mandatory_assets(self) -> bool:
        kinds = set(self.assets.values_list("kind", flat=True))
        return "model" in kinds and "reference_data" in kinds

    def can_build(self) -> bool:
        return (
            self.has_mandatory_assets()
            and not self.is_dirty
            and self.saved_snapshot_id is not None
            and self.status != "locked"
        )


class ModelDraftRevision(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    draft = models.ForeignKey(ModelDraft, on_delete=models.CASCADE, related_name="revisions")
    number = models.PositiveIntegerField()
    flavor = models.CharField(max_length=80, blank=True)
    artifact_format = models.CharField(max_length=20, default="raw")
    requirements_snapshot = models.TextField(blank=True)
    source_version = models.ForeignKey(
        "registry.ModelVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="draft_revisions"
    )
    saved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-number"]
        constraints = [models.UniqueConstraint(fields=["draft", "number"], name="draft_revision_number_unique")]


class DraftRevisionAsset(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    revision = models.ForeignKey(ModelDraftRevision, on_delete=models.CASCADE, related_name="assets")
    kind = models.CharField(max_length=40)
    name = models.CharField(max_length=255)
    uri = models.CharField(max_length=1024)
    checksum = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=160, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["revision", "kind"], name="draft_revision_asset_kind_unique")]


class DraftAssetUpload(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    draft = models.ForeignKey(ModelDraft, on_delete=models.CASCADE, related_name="uploads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="draft_asset_uploads")
    kind = models.CharField(max_length=40)
    object_key = models.CharField(max_length=1024, unique=True)
    filename = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    checksum = models.CharField(max_length=128)
    content_type = models.CharField(max_length=160)
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class DraftAsset(models.Model):
    KINDS = (
        ("model", "Model Artifact"),
        ("reference_data", "Reference Baseline Data"),
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
    draft = models.ForeignKey(ModelDraft, on_delete=models.CASCADE, related_name="assets")
    kind = models.CharField(max_length=40, choices=KINDS)
    name = models.CharField(max_length=255)
    s3_uri = models.CharField(max_length=1024)
    checksum = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=160, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["draft", "kind"], name="draft_asset_kind_unique")
        ]

    def __str__(self):
        return f"{self.draft.project.name}:draft/{self.kind}/{self.name}"
