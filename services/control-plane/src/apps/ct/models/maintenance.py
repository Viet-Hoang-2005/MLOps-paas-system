from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.ct.models.base import PublicModel, VersionReferenceModel


class MaintenanceDecision(VersionReferenceModel):
    version_reference_fields = ("expected_champion_id",)
    ACTIONS = (("keep", "Keep"), ("request_labels", "Request labels"), ("hold", "Hold"), ("retrain", "Retrain"))

    window = models.ForeignKey("ct.EvidenceWindow", on_delete=models.PROTECT, related_name="decisions")
    policy = models.ForeignKey("ct.MaintenancePolicy", on_delete=models.PROTECT, related_name="decisions")
    expected_champion = models.ForeignKey(
        "registry.ModelVersion", on_delete=models.PROTECT, related_name="maintenance_decisions"
    )
    evaluation_attempt = models.PositiveSmallIntegerField(default=1)
    action = models.CharField(max_length=24, choices=ACTIONS)
    reason_code = models.CharField(max_length=80)
    reason_detail = models.TextField(blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    verify_label_count = models.PositiveIntegerField(default=0)
    train_label_count = models.PositiveIntegerField(default=0)
    gate_label_count = models.PositiveIntegerField(default=0)
    training_job = models.ForeignKey(
        "training.TrainingJob", on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_decisions"
    )
    decided_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["window", "policy", "evaluation_attempt"], name="ct_decision_window_policy_attempt"
            )
        ]

    def __str__(self):
        return f"Maintenance decision {self.public_id}"


class MaintenanceRun(VersionReferenceModel):
    version_reference_fields = ("expected_champion_id", "candidate_id")
    ACTIVE_STATES = ("awaiting_execution", "running", "awaiting_gate", "awaiting_update")
    STATES = tuple(
        (value, value.replace("_", " ").title())
        for value in (*ACTIVE_STATES, "applied", "failed", "expired", "superseded")
    )

    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="maintenance_runs")
    decision = models.OneToOneField("ct.MaintenanceDecision", on_delete=models.PROTECT, related_name="maintenance_run")
    expected_champion = models.ForeignKey(
        "registry.ModelVersion", on_delete=models.PROTECT, related_name="expected_maintenance_runs"
    )
    state = models.CharField(max_length=32, choices=STATES, default="awaiting_execution")
    dataset_snapshot = models.ForeignKey(
        "ct.DatasetSnapshot", on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_runs"
    )
    training_job = models.ForeignKey(
        "training.TrainingJob", on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_runs"
    )
    candidate = models.ForeignKey(
        "registry.ModelVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="candidate_maintenance_runs",
    )
    deployment = models.ForeignKey(
        "deployment.Deployment", on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_runs"
    )
    deadline_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(state__in=("awaiting_execution", "running", "awaiting_gate", "awaiting_update")),
                name="ct_one_active_run_per_project",
            )
        ]

    def __str__(self):
        return f"Maintenance run {self.public_id}"


class MaintenanceStepAttempt(PublicModel):
    STEPS = (
        ("snapshot", "Snapshot"),
        ("training", "Training"),
        ("build", "Build"),
        ("gate", "Gate"),
        ("update", "Update"),
        ("verify_runtime", "Verify runtime"),
    )
    STATUSES = (
        ("pending", "Pending"),
        ("dispatched", "Dispatched"),
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("unknown", "Unknown"),
    )

    run = models.ForeignKey("ct.MaintenanceRun", on_delete=models.CASCADE, related_name="step_attempts")
    step = models.CharField(max_length=32, choices=STEPS)
    attempt_number = models.PositiveSmallIntegerField()
    backend = models.CharField(max_length=30)
    workflow_uid = models.CharField(max_length=255, blank=True)
    workload_uid = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="pending")
    idempotency_key = models.CharField(max_length=255, unique=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "step", "attempt_number"], name="ct_step_run_attempt_unique")
        ]

    def __str__(self):
        return f"Maintenance step {self.public_id}"
