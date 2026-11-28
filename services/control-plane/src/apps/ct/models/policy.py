from django.db import models
from django.db.models import Q

from apps.ct.models.base import PublicModel


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

    def __str__(self):
        return f"Policy {self.public_id}"
