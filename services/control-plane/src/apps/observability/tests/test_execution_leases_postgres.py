from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, connections, transaction

from apps.catalog.models import ModelProject
from apps.training.models import TrainingJob
from apps.observability.services.executions import claim
from apps.observability.services import executions


@pytest.mark.django_db(transaction=True)
def test_concurrent_claims_have_one_owner_per_job(settings):
    if connection.vendor != "postgresql":
        pytest.skip("Lease concurrency requires disposable PostgreSQL.")
    owner = get_user_model().objects.create_user("leases@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="lease-concurrency")
    TrainingJob.objects.bulk_create([TrainingJob(project=project, name=f"job-{index}", model_flavor="sklearn", backend="docker", status="queued") for index in range(24)])
    gate = Barrier(3)

    def claimant():
        try:
            gate.wait(timeout=10)
            return claim("training")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=3) as workers:
        batches = list(workers.map(lambda _: claimant(), range(3)))
    ids = [public_id for batch in batches for public_id, token in batch]
    assert len(ids) == 24
    assert len(set(ids)) == 24
    assert claim("training") == []


@pytest.fixture
def postgres_job(settings):
    if connection.vendor != "postgresql":
        pytest.skip("Observation concurrency requires disposable PostgreSQL.")
    owner = get_user_model().objects.create_user("observations@example.com", "password123")
    project = ModelProject.objects.create(owner=owner, name="observation-concurrency")
    return TrainingJob.objects.create(project=project, name="job", model_flavor="sklearn", backend="docker", status="running")


@pytest.mark.django_db(transaction=True)
def test_concurrent_observation_replay_consumes_lease_once(postgres_job):
    job = postgres_job
    token = claim("training", job.public_id)[0][1]
    gate = Barrier(2)

    def report():
        try:
            gate.wait(timeout=10)
            return executions.apply_observation("training", job.public_id, token, {"status": "running"})
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: report(), range(2)))
    assert sorted(results) == ["ignored", "running"]


@pytest.mark.django_db(transaction=True)
def test_cancellation_lock_prevents_concurrent_completion(postgres_job, monkeypatch):
    job = postgres_job
    token = claim("training", job.public_id)[0][1]
    verified = Event()
    monkeypatch.setattr(executions, "_completion_data", Mock(side_effect=lambda row, kind: verified.set()))

    def report():
        try:
            return executions.apply_observation("training", job.public_id, token, {"status": "completed"})
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as workers:
        with transaction.atomic():
            ModelProject.objects.select_for_update().get(pk=job.project_id)
            TrainingJob.objects.select_for_update().filter(pk=job.pk).update(status="cancelling", execution_stop_requested=True)
            result = workers.submit(report)
            assert verified.wait(timeout=10)
        assert result.result(timeout=10) == "cancelling"
    job.refresh_from_db()
    assert job.status == "cancelling" and not job.outputs.exists()
    assert job.observation_status == "cleanup_pending"
