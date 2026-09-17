import uuid

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class PublicModel(models.Model):
    """Common internal bigint primary key plus externally safe UUID."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        abstract = True


class MaintenancePolicy(PublicModel):
    KINDS = tuple((f"b{i}", f"B{i}") for i in range(6))

    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="maintenance_policies")
    version = models.PositiveIntegerField()
    policy_kind = models.CharField(max_length=4, choices=KINDS)
    config = models.JSONField(default=dict)
    checksum = models.CharField(max_length=128)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "version"], name="ct_policy_project_version_unique"),
            models.UniqueConstraint(
                fields=["project"], condition=Q(is_active=True), name="ct_one_active_policy_per_project"
            ),
        ]


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


class EvidenceWindow(PublicModel):
    STATUSES = (
        ("collecting", "Collecting"),
        ("sealed", "Sealed"),
        ("awaiting_labels", "Awaiting labels"),
        ("decided", "Decided"),
        ("invalid", "Invalid"),
    )

    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="evidence_windows")
    champion = models.ForeignKey("registry.ModelVersion", on_delete=models.PROTECT, related_name="champion_evidence_windows")
    policy = models.ForeignKey("ct.MaintenancePolicy", on_delete=models.PROTECT, related_name="evidence_windows")
    reference_snapshot = models.ForeignKey("ct.DatasetSnapshot", on_delete=models.PROTECT, related_name="reference_evidence_windows")
    ordinal = models.PositiveBigIntegerField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    prediction_manifest_uri = models.CharField(max_length=1024, blank=True)
    prediction_manifest_checksum = models.CharField(max_length=128, blank=True)
    sample_count = models.PositiveBigIntegerField(default=0)
    drift_run = models.ForeignKey("drift.DriftRun", on_delete=models.SET_NULL, null=True, blank=True, related_name="evidence_windows")
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


class EvidenceWindowSample(PublicModel):
    POOLS = (("hidden", "Hidden"), ("verify", "Verify"), ("train", "Train"), ("gate", "Gate"))
    QUALITY_STATUSES = (("unchecked", "Unchecked"), ("accepted", "Accepted"), ("rejected", "Rejected"))

    window = models.ForeignKey("ct.EvidenceWindow", on_delete=models.CASCADE, related_name="samples")
    prediction = models.OneToOneField("production.PredictionRecord", on_delete=models.PROTECT, related_name="evidence_window_sample")
    pool = models.CharField(max_length=16, choices=POOLS, default="hidden")
    randomized_rank = models.PositiveBigIntegerField()
    quality_status = models.CharField(max_length=16, choices=QUALITY_STATUSES, default="unchecked")
    quality_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["window", "pool", "randomized_rank"], name="ct_window_pool_rank_unique")]


class LabelBudget(PublicModel):
    STATUSES = (("open", "Open"), ("exhausted", "Exhausted"), ("closed", "Closed"))

    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="label_budgets")
    episode_key = models.CharField(max_length=160)
    total_quota = models.PositiveIntegerField()
    verify_quota = models.PositiveIntegerField(default=0)
    train_quota = models.PositiveIntegerField(default=0)
    gate_quota = models.PositiveIntegerField(default=0)
    verify_held = models.PositiveIntegerField(default=0)
    train_held = models.PositiveIntegerField(default=0)
    gate_held = models.PositiveIntegerField(default=0)
    verify_used = models.PositiveIntegerField(default=0)
    train_used = models.PositiveIntegerField(default=0)
    gate_used = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUSES, default="open")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "episode_key"], name="ct_budget_project_episode_unique"),
            models.CheckConstraint(check=Q(verify_quota__lte=F("total_quota")) & Q(train_quota__lte=F("total_quota")) & Q(gate_quota__lte=F("total_quota")), name="ct_budget_purpose_quota_valid"),
            models.CheckConstraint(check=Q(verify_held__lte=F("verify_quota") - F("verify_used")) & Q(train_held__lte=F("train_quota") - F("train_used")) & Q(gate_held__lte=F("gate_quota") - F("gate_used")), name="ct_budget_purpose_usage_valid"),
            models.CheckConstraint(check=Q(verify_quota__gte=F("verify_held") + F("verify_used")) & Q(train_quota__gte=F("train_held") + F("train_used")) & Q(gate_quota__gte=F("gate_held") + F("gate_used")), name="ct_budget_purpose_total_valid"),
            models.CheckConstraint(check=Q(total_quota__gte=F("verify_held") + F("verify_used") + F("train_held") + F("train_used") + F("gate_held") + F("gate_used")), name="ct_budget_total_usage_valid"),
        ]


class LabelRequest(PublicModel):
    PURPOSES = (("verify", "Verify"), ("train", "Train"), ("gate", "Gate"))
    STATUSES = (("pending", "Pending"), ("fulfilled", "Fulfilled"), ("rejected", "Rejected"), ("cancelled", "Cancelled"), ("expired", "Expired"))

    window = models.ForeignKey("ct.EvidenceWindow", on_delete=models.CASCADE, related_name="label_requests")
    budget = models.ForeignKey("ct.LabelBudget", on_delete=models.PROTECT, related_name="requests")
    purpose = models.CharField(max_length=16, choices=PURPOSES)
    seed = models.BigIntegerField()
    request_round = models.PositiveSmallIntegerField()
    requested_count = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=STATUSES, default="pending")
    idempotency_key = models.CharField(max_length=255, unique=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["window", "purpose", "request_round"], name="ct_request_window_purpose_round")]


class LabelRequestItem(PublicModel):
    STATUSES = (("reserved", "Reserved"), ("revealed", "Revealed"), ("released", "Released"), ("rejected", "Rejected"))

    request = models.ForeignKey("ct.LabelRequest", on_delete=models.CASCADE, related_name="items")
    window_sample = models.OneToOneField("ct.EvidenceWindowSample", on_delete=models.PROTECT, related_name="label_request_item")
    status = models.CharField(max_length=16, choices=STATUSES, default="reserved")
    unit_cost = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Feedback(PublicModel):
    SOURCES = (("human", "Human"), ("evaluator", "Evaluator"), ("import", "Import"))

    prediction = models.OneToOneField("production.PredictionRecord", on_delete=models.PROTECT, related_name="feedback")
    request_item = models.OneToOneField("ct.LabelRequestItem", on_delete=models.PROTECT, related_name="feedback")
    true_label = models.TextField()
    source = models.CharField(max_length=16, choices=SOURCES)
    checksum = models.CharField(max_length=128, blank=True)
    revealed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class LabelLedgerEntry(PublicModel):
    PURPOSES = LabelRequest.PURPOSES
    TYPES = (("reserve", "Reserve"), ("commit", "Commit"), ("release", "Release"))

    budget = models.ForeignKey("ct.LabelBudget", on_delete=models.PROTECT, related_name="ledger_entries")
    request = models.ForeignKey("ct.LabelRequest", on_delete=models.PROTECT, related_name="ledger_entries")
    item = models.ForeignKey("ct.LabelRequestItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_entries")
    purpose = models.CharField(max_length=16, choices=PURPOSES)
    entry_type = models.CharField(max_length=16, choices=TYPES)
    units = models.PositiveIntegerField()
    idempotency_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MaintenanceDecision(PublicModel):
    ACTIONS = (("keep", "Keep"), ("request_labels", "Request labels"), ("hold", "Hold"), ("retrain", "Retrain"))

    window = models.ForeignKey("ct.EvidenceWindow", on_delete=models.PROTECT, related_name="decisions")
    policy = models.ForeignKey("ct.MaintenancePolicy", on_delete=models.PROTECT, related_name="decisions")
    expected_champion = models.ForeignKey("registry.ModelVersion", on_delete=models.PROTECT, related_name="maintenance_decisions")
    evaluation_attempt = models.PositiveSmallIntegerField(default=1)
    action = models.CharField(max_length=24, choices=ACTIONS)
    reason_code = models.CharField(max_length=80)
    reason_detail = models.TextField(blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    verify_label_count = models.PositiveIntegerField(default=0)
    train_label_count = models.PositiveIntegerField(default=0)
    gate_label_count = models.PositiveIntegerField(default=0)
    training_job = models.ForeignKey("training.TrainingJob", on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_decisions")
    decided_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["window", "policy", "evaluation_attempt"], name="ct_decision_window_policy_attempt")]


class MaintenanceRun(PublicModel):
    ACTIVE_STATES = ("awaiting_execution", "running", "awaiting_gate", "awaiting_update")
    STATES = tuple((value, value.replace("_", " ").title()) for value in (*ACTIVE_STATES, "applied", "failed", "expired", "superseded"))

    project = models.ForeignKey("catalog.ModelProject", on_delete=models.CASCADE, related_name="maintenance_runs")
    decision = models.OneToOneField("ct.MaintenanceDecision", on_delete=models.PROTECT, related_name="maintenance_run")
    expected_champion = models.ForeignKey("registry.ModelVersion", on_delete=models.PROTECT, related_name="expected_maintenance_runs")
    state = models.CharField(max_length=32, choices=STATES, default="awaiting_execution")
    dataset_snapshot = models.ForeignKey("ct.DatasetSnapshot", on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_runs")
    training_job = models.ForeignKey("training.TrainingJob", on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_runs")
    candidate = models.ForeignKey("registry.ModelVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="candidate_maintenance_runs")
    deployment = models.ForeignKey("deployment.Deployment", on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_runs")
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


class MaintenanceStepAttempt(PublicModel):
    STEPS = (("snapshot", "Snapshot"), ("training", "Training"), ("build", "Build"), ("gate", "Gate"), ("update", "Update"), ("verify_runtime", "Verify runtime"))
    STATUSES = (("pending", "Pending"), ("dispatched", "Dispatched"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("cancelled", "Cancelled"), ("unknown", "Unknown"))

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
        constraints = [models.UniqueConstraint(fields=["run", "step", "attempt_number"], name="ct_step_run_attempt_unique")]


class EvaluationGate(PublicModel):
    STATUSES = (("pending", "Pending"), ("running", "Running"), ("pass", "Pass"), ("fail", "Fail"), ("hold", "Hold"), ("error", "Error"))

    run = models.OneToOneField("ct.MaintenanceRun", on_delete=models.PROTECT, related_name="evaluation_gate")
    candidate = models.ForeignKey("registry.ModelVersion", on_delete=models.PROTECT, related_name="candidate_evaluation_gates")
    champion = models.ForeignKey("registry.ModelVersion", on_delete=models.PROTECT, related_name="champion_evaluation_gates")
    gate_snapshot = models.ForeignKey("ct.DatasetSnapshot", on_delete=models.PROTECT, related_name="evaluation_gates")
    status = models.CharField(max_length=16, choices=STATUSES, default="pending")
    metric_name = models.CharField(max_length=80, blank=True)
    candidate_value = models.FloatField(null=True, blank=True)
    champion_value = models.FloatField(null=True, blank=True)
    delta = models.FloatField(null=True, blank=True)
    margin = models.FloatField(null=True, blank=True)
    historical_result = models.JSONField(default=dict, blank=True)
    evidence_uri = models.CharField(max_length=1024, blank=True)
    evidence_checksum = models.CharField(max_length=128, blank=True)
    reason = models.TextField(blank=True)
    evaluated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(check=~Q(candidate=F("champion")), name="ct_gate_distinct_versions")]
