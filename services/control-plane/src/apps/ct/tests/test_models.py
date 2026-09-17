from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

from apps.catalog.models import ModelProject
from apps.ct.models import (
    DatasetSnapshot,
    EvidenceWindow,
    LabelBudget,
    MaintenanceDecision,
    MaintenancePolicy,
    MaintenanceRun,
)


@pytest.mark.django_db
def test_only_one_active_policy_is_allowed_per_project():
    owner = get_user_model().objects.create_user("policy@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="CT policy")
    MaintenancePolicy.objects.create(project=project, version=1, policy_kind="b0", checksum="a", is_active=True)

    with pytest.raises(IntegrityError):
        MaintenancePolicy.objects.create(project=project, version=2, policy_kind="b1", checksum="b", is_active=True)


@pytest.mark.django_db
def test_label_budget_cannot_hold_or_spend_beyond_quota():
    owner = get_user_model().objects.create_user("budget@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="CT budget")

    with pytest.raises(IntegrityError):
        LabelBudget.objects.create(
            project=project, episode_key="episode-1", total_quota=1, verify_quota=1,
            verify_held=1, verify_used=1,
        )


@pytest.mark.django_db
def test_only_one_active_maintenance_run_is_allowed_per_project():
    owner = get_user_model().objects.create_user("run@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="CT run")
    champion = project.versions.create(version="1")
    policy = MaintenancePolicy.objects.create(project=project, version=1, policy_kind="b0", checksum="a", is_active=True)
    snapshot = DatasetSnapshot.objects.create(
        project=project, role="reference", manifest_uri="s3://bucket/reference.json", manifest_checksum="m", schema_checksum="s"
    )
    now = timezone.now()
    window = EvidenceWindow.objects.create(
        project=project, champion=champion, policy=policy, reference_snapshot=snapshot,
        ordinal=1, starts_at=now, ends_at=now + timedelta(hours=1),
    )
    decision = MaintenanceDecision.objects.create(
        window=window, policy=policy, expected_champion=champion,
        action="hold", reason_code="test",
    )
    MaintenanceRun.objects.create(project=project, decision=decision, expected_champion=champion, state="running")
    second_decision = MaintenanceDecision.objects.create(
        window=window, policy=policy, expected_champion=champion, evaluation_attempt=2,
        action="hold", reason_code="test",
    )

    with pytest.raises(IntegrityError):
        MaintenanceRun.objects.create(
            project=project, decision=second_decision, expected_champion=champion, state="awaiting_gate"
        )
