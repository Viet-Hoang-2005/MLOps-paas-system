import uuid

from django.db import models


class ModelVersion(models.Model):
    STAGES = (("none", "None"), ("staging", "Staging"), ("production", "Production"), ("archived", "Archived"))
    DEPLOYABILITY = (
        ("unknown", "Unknown"),
        ("deployable", "Deployable"),
        ("track_only", "Track Only"),
        ("invalid", "Invalid"),
    )

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="versions")
    source_job = models.ForeignKey(
        "training.TrainingJob", on_delete=models.SET_NULL, related_name="registered_versions", null=True, blank=True
    )
    source_job_reference = models.UUIDField(null=True, blank=True, db_index=True)
    version = models.CharField(max_length=80)
    requirements_snapshot = models.TextField(blank=True)
    flavor = models.CharField(max_length=80, blank=True)
    stage = models.CharField(max_length=20, choices=STAGES, default="none")
    deployability = models.CharField(max_length=30, choices=DEPLOYABILITY, default="unknown")
    deployability_reason = models.TextField(blank=True)
    metrics_summary = models.JSONField(default=dict, blank=True)
    params_summary = models.JSONField(default=dict, blank=True)
    insights_summary = models.JSONField(default=dict, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-registered_at"]
        constraints = [
            models.UniqueConstraint(fields=["project", "version"], name="registry_project_version_unique"),
            models.UniqueConstraint(
                fields=["source_job"],
                condition=models.Q(source_job__isnull=False),
                name="registry_source_job_unique",
            ),
        ]

    def __str__(self):
        return f"{self.project.name}@{self.version}"


class ModelArtifact(models.Model):
    KINDS = (
        ("source", "Source"),
        ("training_output", "Training Output"),
        ("package", "Package"),
        ("label_mapping", "Label Mapping"),
        ("mlflow", "MLflow"),
        ("image", "Image"),
        ("metrics", "Metrics"),
        ("params", "Parameters"),
        ("model_insights", "Model Insights"),
        ("feature_importance", "Feature Importance"),
        ("input_schema", "Input Schema"),
    )
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    version = models.ForeignKey(ModelVersion, on_delete=models.CASCADE, related_name="artifacts")
    kind = models.CharField(max_length=40, choices=KINDS)
    name = models.CharField(max_length=255)
    uri = models.CharField(max_length=1024)
    checksum = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=160, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["version", "kind", "name"], name="registry_artifact_unique")]

    def __str__(self):
        return f"{self.version}: {self.kind}/{self.name}"


class ModelMetric(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    version = models.ForeignKey(ModelVersion, on_delete=models.CASCADE, related_name="metrics")
    name = models.CharField(max_length=160)
    value = models.FloatField()
    step = models.IntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.version}: {self.name}={self.value}"


class RegistryAlias(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="aliases")
    version = models.ForeignKey(ModelVersion, on_delete=models.PROTECT, related_name="aliases")
    name = models.CharField(max_length=80)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "name"], name="registry_project_alias_unique")]

    def __str__(self):
        return f"{self.project.name}:{self.name} -> {self.version.version}"


class RegistryEvent(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    version = models.ForeignKey(ModelVersion, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey("identity.CustomUser", on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=60)
    from_state = models.CharField(max_length=80, blank=True)
    to_state = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.version}: {self.event_type}"
