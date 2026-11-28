from django.db import models
from django.db.models import F, Q

from apps.ct.models.base import VersionReferenceModel


class EvaluationGate(VersionReferenceModel):
    version_reference_fields = ("champion_id", "candidate_id")
    STATUSES = (
        ("pending", "Pending"),
        ("running", "Running"),
        ("pass", "Pass"),
        ("fail", "Fail"),
        ("hold", "Hold"),
        ("error", "Error"),
    )

    run = models.OneToOneField("ct.MaintenanceRun", on_delete=models.PROTECT, related_name="evaluation_gate")
    candidate = models.ForeignKey(
        "registry.ModelVersion", on_delete=models.PROTECT, related_name="candidate_evaluation_gates"
    )
    champion = models.ForeignKey(
        "registry.ModelVersion", on_delete=models.PROTECT, related_name="champion_evaluation_gates"
    )
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

    def __str__(self):
        return f"Evaluation gate {self.public_id}"
