from django.db import models
from django.db.models import F, Q

from apps.ct.models.base import PublicModel, VersionReferenceModel


class DatasetSnapshot(PublicModel):
    ROLES = (
        ("initial_train", "Initial train"),
        ("calibration", "Calibration"),
        ("reference", "Reference"),
        ("retrain", "Retrain"),
        ("gate", "Gate"),
        ("historical_holdout", "Historical holdout"),
    )

    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="dataset_snapshots")
    role = models.CharField(max_length=32, choices=ROLES)
    source_window = models.ForeignKey(
        "ct.EvidenceWindow", on_delete=models.SET_NULL, related_name="derived_snapshots", null=True, blank=True
    )
    manifest_uri = models.CharField(max_length=1024)
    manifest_checksum = models.CharField(max_length=128)
    schema_checksum = models.CharField(max_length=128)
    code_checksum = models.CharField(max_length=128, blank=True)
    code_snapshot_uri = models.CharField(max_length=1024, blank=True)
    row_count = models.PositiveBigIntegerField(default=0)
    recipe_version = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    sealed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Dataset snapshot {self.public_id}"


class EvidenceWindow(VersionReferenceModel):
    version_reference_fields = ("champion_id",)
    STATUSES = (
        ("collecting", "Collecting"),
        ("sealed", "Sealed"),
        ("awaiting_labels", "Awaiting labels"),
        ("decided", "Decided"),
        ("invalid", "Invalid"),
    )

    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="evidence_windows")
    champion = models.ForeignKey(
        "registry.ModelVersion", on_delete=models.PROTECT, related_name="champion_evidence_windows"
    )
    policy = models.ForeignKey("ct.MaintenancePolicy", on_delete=models.PROTECT, related_name="evidence_windows")
    reference_snapshot = models.ForeignKey(
        "ct.DatasetSnapshot", on_delete=models.PROTECT, related_name="reference_evidence_windows"
    )
    ordinal = models.PositiveBigIntegerField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    prediction_manifest_uri = models.CharField(max_length=1024, blank=True)
    prediction_manifest_checksum = models.CharField(max_length=128, blank=True)
    sample_count = models.PositiveBigIntegerField(default=0)
    drift_run = models.ForeignKey(
        "drift.DriftRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="evidence_windows"
    )
    estimator = models.JSONField(default=dict, blank=True)
    verification = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, choices=STATUSES, default="collecting")
    sealed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "policy", "ordinal"], name="ct_window_project_policy_ordinal"),
            models.CheckConstraint(check=Q(ends_at__gt=F("starts_at")), name="ct_window_valid_range"),
        ]

    def __str__(self):
        return f"Evidence window {self.public_id}"


class EvidenceWindowSample(PublicModel):
    POOLS = (("hidden", "Hidden"), ("verify", "Verify"), ("train", "Train"), ("gate", "Gate"))
    QUALITY_STATUSES = (("unchecked", "Unchecked"), ("accepted", "Accepted"), ("rejected", "Rejected"))

    window = models.ForeignKey("ct.EvidenceWindow", on_delete=models.CASCADE, related_name="samples")
    prediction = models.OneToOneField(
        "production.PredictionRecord", on_delete=models.PROTECT, related_name="evidence_window_sample"
    )
    pool = models.CharField(max_length=16, choices=POOLS, default="hidden")
    randomized_rank = models.PositiveBigIntegerField()
    quality_status = models.CharField(max_length=16, choices=QUALITY_STATUSES, default="unchecked")
    quality_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["window", "pool", "randomized_rank"], name="ct_window_pool_rank_unique")
        ]

    def __str__(self):
        return f"Evidence sample {self.public_id}"
