from datetime import datetime, timedelta, timezone as dt_timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from unittest.mock import Mock
from rest_framework.test import APIClient

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob, TrainingQuotaReservation
from apps.training.services.quota import (QuotaExceeded, TrainingConcurrencyExceeded, lock_owner, reserve,
                                           update_observation, usage, week_start)


@pytest.fixture
def job(db, settings):
    settings.TRAINING_BACKEND = "argo"
    settings.TRAINING_EXECUTION_WATCH_ENABLED = True
    owner = get_user_model().objects.create_user("quota@example.com")
    project = ModelProject.objects.create(owner=owner, name="quota")
    return TrainingJob.objects.create(project=project, name="job", backend="argo", model_flavor="pytorch",
                                      vcpu=2, memory_mb=4096, max_runtime_seconds=3600)


def reserve_locked(job):
    with transaction.atomic():
        lock_owner(job.project.owner_id)
        reserve(job)


def test_reservation_and_concurrency_across_projects(job):
    reserve_locked(job)
    resource = next(v for v in usage(job.project.owner)["resources"] if v["resource"] == "cpu_medium")
    assert resource["reserved_seconds"] == 3600 and resource["used_seconds"] == 0
    second = TrainingJob.objects.create(project=ModelProject.objects.create(owner=job.project.owner, name="second"),
                                        name="job2", backend="argo", model_flavor="pytorch")
    with pytest.raises(TrainingConcurrencyExceeded):
        reserve_locked(second)


def test_gpu_charges_only_gpu_quota_and_enforces_limit(job, settings, monkeypatch):
    monkeypatch.setattr("apps.training.services.quota.timezone.now", lambda: datetime(2026, 11, 4, tzinfo=dt_timezone.utc))
    job.accelerator_type, job.accelerator_model = "gpu", "a10g"
    job.max_runtime_seconds = settings.TRAINING_GPU_A10G_WEEKLY_SECONDS + 1
    with pytest.raises(QuotaExceeded):
        reserve_locked(job)
    job.max_runtime_seconds = 3600
    reserve_locked(job)
    values = {v["resource"]: v for v in usage(job.project.owner)["resources"]}
    assert values["a10g"]["reserved_seconds"] == 3600
    assert values["cpu_medium"]["reserved_seconds"] == 0


def test_runtime_cap_and_token_cover_24_hours(job, settings):
    from apps.training.services.capabilities import _ttl_seconds
    from apps.training.services.resources import runtime_options, validate_resources
    settings.TRAINING_MAX_RUNTIME_SECONDS = 86400
    settings.TRAINING_CAPABILITY_MAX_TTL_SECONDS = 0
    assert 86400 in runtime_options()
    validate_resources({"max_runtime_seconds": 86400}, job)
    job.max_runtime_seconds = 86400
    assert _ttl_seconds(job) == 89100
    settings.TRAINING_BACKEND = "docker"
    settings.TRAINING_MAX_RUNTIME_SECONDS = 5400
    assert runtime_options() == [900, 1800, 3600, 5400]


def test_actual_usage_spans_weeks_and_survives_job_deletion(job, monkeypatch):
    start = datetime(2026, 11, 8, 23, 30, tzinfo=dt_timezone.utc)
    monkeypatch.setattr("apps.training.services.quota.timezone.now", lambda: start)
    reserve_locked(job)
    with transaction.atomic():
        lock_owner(job.project.owner_id)
        update_observation(job, started_at=start)
        update_observation(job, finished_at=start + timedelta(hours=1), stopped=True)
    reservation = TrainingQuotaReservation.objects.get(job_id=job.public_id)
    assert not reservation.active
    assert list(reservation.weeks.order_by("week_start").values_list("used_seconds", flat=True)) == [1800, 1800]
    job.delete()
    assert TrainingQuotaReservation.objects.filter(pk=reservation.pk).exists()


def test_reservation_is_released_only_after_confirmed_stop(job, monkeypatch):
    start = datetime(2026, 11, 4, tzinfo=dt_timezone.utc)
    monkeypatch.setattr("apps.training.services.quota.timezone.now", lambda: start)
    reserve_locked(job)
    with transaction.atomic():
        lock_owner(job.project.owner_id)
        update_observation(job, started_at=start, finished_at=start + timedelta(minutes=10))
    reservation = TrainingQuotaReservation.objects.get(job_id=job.public_id)
    assert reservation.active and reservation.weeks.first().reserved_seconds == 3600
    with transaction.atomic():
        lock_owner(job.project.owner_id)
        assert update_observation(job, stopped=True)
        assert update_observation(job, stopped=True)
    reservation.refresh_from_db()
    assert not reservation.active
    assert reservation.weeks.first().used_seconds == 600
    assert reservation.weeks.first().reserved_seconds == 0


def test_unconfirmed_runtime_timing_keeps_reservation(job):
    reserve_locked(job)
    job.external_job_id = "training-unknown"
    with transaction.atomic():
        lock_owner(job.project.owner_id)
        assert not update_observation(job, stopped=True)
    assert TrainingQuotaReservation.objects.get(job_id=job.public_id).active


def test_utc_reset_and_local_unlimited(job, settings):
    assert week_start(datetime(2026, 11, 9, 1, tzinfo=dt_timezone.utc)) == datetime(2026, 11, 9, tzinfo=dt_timezone.utc)
    settings.TRAINING_BACKEND = "docker"
    assert all(v["limit_seconds"] is None for v in usage(job.project.owner)["resources"])


def test_usage_is_authenticated_and_scoped(job):
    client = APIClient()
    assert client.get("/api/training-jobs/usage/").status_code == 401
    reserve_locked(job)
    other = get_user_model().objects.create_user("other-quota@example.com")
    client.force_authenticate(other)
    response = client.get("/api/training-jobs/usage/")
    assert response.status_code == 200 and response.data["active_jobs_count"] == 0


def test_submit_enforces_single_active_job_over_all_projects(job):
    job.status = "pending"
    job.save(update_fields=["status"])
    second = TrainingJob.objects.create(project=ModelProject.objects.create(owner=job.project.owner, name="other project"),
                                        name="second", backend="argo", model_flavor="pytorch")
    client = APIClient()
    client.force_authenticate(job.project.owner)
    assert client.post(f"/api/training-jobs/{job.public_id}/submit/").status_code == 202
    response = client.post(f"/api/training-jobs/{second.public_id}/submit/")
    assert response.status_code == 409
    assert response.data["error"]["code"] == "training_concurrency_exceeded"
    second.refresh_from_db()
    assert second.status == "pending"


@pytest.mark.parametrize("training_enabled,drift_enabled,expected", [
    (False, False, []),
    (True, False, ["training"]),
    (False, True, ["drift"]),
    (True, True, ["training", "drift"]),
])
def test_execution_watchers_scan_only_enabled_kinds(settings, monkeypatch, training_enabled, drift_enabled, expected):
    from apps.observability.services.executions import scan
    settings.DRIFT_EXECUTION_WATCH_ENABLED = drift_enabled
    settings.TRAINING_EXECUTION_WATCH_ENABLED = training_enabled
    claim = Mock(return_value=[])
    monkeypatch.setattr("apps.observability.services.executions.claim", claim)
    assert scan() == 0
    assert [call.args[0] for call in claim.call_args_list] == expected


@pytest.mark.django_db(transaction=True)
def test_postgres_simultaneous_submit_only_one_succeeds(job, monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL is required to test row locking")
    from apps.training.services.jobs import submit_job
    job.status = "pending"
    job.save(update_fields=["status"])
    second = TrainingJob.objects.create(project=job.project, name="second", backend="argo", model_flavor="pytorch")
    monkeypatch.setattr("apps.training.services.jobs._enqueue", lambda _job: None)
    barrier = Barrier(2)
    def submit(job_id):
        close_old_connections()
        try:
            item = TrainingJob.objects.select_related("project").get(pk=job_id)
            barrier.wait(timeout=10)
            try:
                submit_job(item)
                return "submitted"
            except TrainingConcurrencyExceeded:
                return "rejected"
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, [job.pk, second.pk]))
    assert sorted(outcomes) == ["rejected", "submitted"]
