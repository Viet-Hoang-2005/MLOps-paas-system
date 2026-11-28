from django.db import models
from django.db.models import F, Q

from apps.ct.models.base import PublicModel


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
            models.CheckConstraint(
                check=Q(verify_quota__lte=F("total_quota"))
                & Q(train_quota__lte=F("total_quota"))
                & Q(gate_quota__lte=F("total_quota")),
                name="ct_budget_purpose_quota_valid",
            ),
            models.CheckConstraint(
                check=Q(verify_held__lte=F("verify_quota") - F("verify_used"))
                & Q(train_held__lte=F("train_quota") - F("train_used"))
                & Q(gate_held__lte=F("gate_quota") - F("gate_used")),
                name="ct_budget_purpose_usage_valid",
            ),
            models.CheckConstraint(
                check=Q(verify_quota__gte=F("verify_held") + F("verify_used"))
                & Q(train_quota__gte=F("train_held") + F("train_used"))
                & Q(gate_quota__gte=F("gate_held") + F("gate_used")),
                name="ct_budget_purpose_total_valid",
            ),
            models.CheckConstraint(
                check=Q(
                    total_quota__gte=F("verify_held")
                    + F("verify_used")
                    + F("train_held")
                    + F("train_used")
                    + F("gate_held")
                    + F("gate_used")
                ),
                name="ct_budget_total_usage_valid",
            ),
        ]

    def __str__(self):
        return f"Label budget {self.public_id}"


class LabelRequest(PublicModel):
    PURPOSES = (("verify", "Verify"), ("train", "Train"), ("gate", "Gate"))
    STATUSES = (
        ("pending", "Pending"),
        ("fulfilled", "Fulfilled"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
        ("expired", "Expired"),
    )

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
        constraints = [
            models.UniqueConstraint(
                fields=["window", "purpose", "request_round"], name="ct_request_window_purpose_round"
            )
        ]

    def __str__(self):
        return f"Label request {self.public_id}"


class LabelRequestItem(PublicModel):
    STATUSES = (("reserved", "Reserved"), ("revealed", "Revealed"), ("released", "Released"), ("rejected", "Rejected"))

    request = models.ForeignKey("ct.LabelRequest", on_delete=models.CASCADE, related_name="items")
    window_sample = models.OneToOneField(
        "ct.EvidenceWindowSample", on_delete=models.PROTECT, related_name="label_request_item"
    )
    status = models.CharField(max_length=16, choices=STATUSES, default="reserved")
    unit_cost = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Label request item {self.public_id}"


class Feedback(PublicModel):
    SOURCES = (("human", "Human"), ("evaluator", "Evaluator"), ("import", "Import"))

    prediction = models.OneToOneField("production.PredictionRecord", on_delete=models.PROTECT, related_name="feedback")
    request_item = models.OneToOneField("ct.LabelRequestItem", on_delete=models.PROTECT, related_name="feedback")
    true_label = models.TextField()
    source = models.CharField(max_length=16, choices=SOURCES)
    checksum = models.CharField(max_length=128, blank=True)
    revealed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback {self.public_id}"


class LabelLedgerEntry(PublicModel):
    PURPOSES = LabelRequest.PURPOSES
    TYPES = (("reserve", "Reserve"), ("commit", "Commit"), ("release", "Release"))

    budget = models.ForeignKey("ct.LabelBudget", on_delete=models.PROTECT, related_name="ledger_entries")
    request = models.ForeignKey("ct.LabelRequest", on_delete=models.PROTECT, related_name="ledger_entries")
    item = models.ForeignKey(
        "ct.LabelRequestItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_entries"
    )
    purpose = models.CharField(max_length=16, choices=PURPOSES)
    entry_type = models.CharField(max_length=16, choices=TYPES)
    units = models.PositiveIntegerField()
    idempotency_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Label ledger entry {self.public_id}"
