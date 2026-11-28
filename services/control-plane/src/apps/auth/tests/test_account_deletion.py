from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auth.account.lifecycle import (
    purge_expired_deleted_accounts_batch,
    purge_user_account,
    stop_user_active_runtimes,
)
from apps.auth.admin import CustomUserPasswordChangeForm
from apps.catalog.models import ModelProject
from apps.deployment.models import Build, Deployment
from apps.drift.models import DriftMonitor, DriftRun
from apps.observability.models import EventOutbox
from apps.registry.models import ModelVersion
from apps.training.tests.factories import training_job
from apps.training.workspace.models import TrainingWorkspace


class FakeStorage:
    def __init__(self):
        self.prefixes = []

    def delete_prefix(self, prefix):
        self.prefixes.append(prefix)


@pytest.fixture
def expired_account(settings):
    settings.ACCOUNT_DELETION_RETENTION_DAYS = 30
    user = get_user_model().objects.create_user(
        "expired-restore@example.com", is_active=False, deleted_at=timezone.now() - timedelta(days=31)
    )
    return user


def reactivate_in_admin(admin_client, user):
    return admin_client.post(
        reverse("admin:identity_customuser_change", args=[user.pk]),
        {"email": user.email, "tenant_id": user.tenant_id, "is_active": "on", "_save": "Save"},
    )


@pytest.mark.django_db
def test_purge_skips_active_user_with_old_deleted_at(expired_account):
    User = get_user_model()
    User.objects.filter(pk=expired_account.pk).update(is_active=True)
    storage = FakeStorage()

    assert purge_user_account(expired_account.pk, storage=storage) == "missing"
    assert purge_expired_deleted_accounts_batch(storage=storage)["purged"] == 0
    expired_account.refresh_from_db()
    assert expired_account.is_active
    assert expired_account.purge_started_at is None
    assert storage.prefixes == []


@pytest.mark.django_db
def test_admin_can_reactivate_before_purge(admin_client, expired_account):
    assert reactivate_in_admin(admin_client, expired_account).status_code == 302
    storage = FakeStorage()

    assert purge_user_account(expired_account.pk, storage=storage) == "missing"
    expired_account.refresh_from_db()
    assert expired_account.is_active
    assert expired_account.deleted_at is None
    assert storage.prefixes == []


@pytest.mark.django_db
def test_failed_storage_purge_keeps_claim_and_allows_retry(admin_client, expired_account):
    class UnavailableStorage:
        def delete_prefix(self, prefix):
            raise TimeoutError("Storage unavailable")

    password_form = CustomUserPasswordChangeForm(
        expired_account, data={"password1": "Admin-test-947!change", "password2": "Admin-test-947!change"}
    )
    assert password_form.is_valid()
    with pytest.raises(TimeoutError):
        purge_user_account(expired_account.pk, storage=UnavailableStorage())
    password_form.save()

    response = reactivate_in_admin(admin_client, expired_account)
    assert response.status_code == 200
    assert b"permanent deletion has started" in response.content
    expired_account.refresh_from_db()
    assert expired_account.purge_started_at is not None
    assert not expired_account.is_active
    assert expired_account.check_password("Admin-test-947!change")
    assert purge_user_account(expired_account.pk, storage=FakeStorage()) == "purged"


@pytest.mark.django_db(transaction=True)
def test_postgres_admin_reactivation_cannot_race_purge(admin_client, expired_account):
    if connection.vendor != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL.")
    started = Event()
    resume = Event()

    class PausingStorage(FakeStorage):
        def delete_prefix(self, prefix):
            started.set()
            assert resume.wait(timeout=15)
            super().delete_prefix(prefix)

    def purge():
        try:
            return purge_expired_deleted_accounts_batch(storage=PausingStorage())
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(purge)
        try:
            assert started.wait(timeout=10)
            storage = FakeStorage()
            assert purge_expired_deleted_accounts_batch(storage=storage)["purged"] == 0
            assert storage.prefixes == []
            response = reactivate_in_admin(admin_client, expired_account)
            assert response.status_code == 200
            assert b"permanent deletion has started" in response.content
        finally:
            resume.set()
        assert future.result(timeout=10)["purged"] == 1


@pytest.mark.django_db
def test_soft_delete_endpoint_marks_user_deleted_and_enqueues_runtime_stop(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    User = get_user_model()
    user = User.objects.create_user("soft-del@example.com", "password123")
    enqueued = []
    monkeypatch.setattr(
        "apps.auth.tasks.stop_user_active_executions.delay",
        lambda user_id: enqueued.append(user_id),
    )

    client = APIClient()
    client.force_authenticate(user)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete("/api/auth/profile/delete/")

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.is_active is False
    assert user.deleted_at is not None
    assert not EventOutbox.objects.filter(aggregate_id=user.public_id, event_type="tenant.disabled").exists()
    assert enqueued == [user.pk]


@pytest.mark.django_db
def test_stop_user_active_runtimes_stops_deployments_and_cancels_active_jobs(monkeypatch):
    User = get_user_model()
    user = User.objects.create_user("runtime-stop@example.com", "password123")
    user.soft_delete()

    project = ModelProject.objects.create(owner=user, name="Runtime Stop Project")
    version = ModelVersion.objects.create(project=project, version="1")
    ready_build = Build.objects.create(project=project, status="succeeded", flavor="sklearn")
    active_deployment = Deployment.objects.create(version=version, build=ready_build, status="succeeded")
    stopped_deployment = Deployment.objects.create(version=version, build=ready_build, status="stopped")
    active_build = Build.objects.create(project=project, status="building", flavor="sklearn")
    active_job = training_job(
        owner=user,
        project=project,
        model_flavor="sklearn",
        vcpu=2,
        memory_mb=4096,
        max_runtime_seconds=3600,
        status="running",
    )
    monitor = DriftMonitor.objects.create(version=version, name="m1", reference_uri="s3://bucket/ref.csv")
    active_run = DriftRun.objects.create(
        monitor=monitor,
        status="running",
        idempotency_key="acct-del-run-1",
    )

    stopped_deployments = []
    cancelled_builds = []
    cancelled_jobs = []
    cancelled_runs = []

    monkeypatch.setattr(
        "apps.deployment.serving.rollout.request_stop",
        lambda item: stopped_deployments.append(item.pk),
    )
    monkeypatch.setattr(
        "apps.deployment.builds.submission.request_cancel",
        lambda item: cancelled_builds.append(item.pk),
    )
    monkeypatch.setattr(
        "apps.training.jobs.lifecycle.cancel_job",
        lambda item: cancelled_jobs.append(item.pk),
    )
    monkeypatch.setattr(
        "apps.drift.runs.lifecycle.request_cancel",
        lambda item: cancelled_runs.append(item.pk),
    )

    counts = stop_user_active_runtimes(user.pk)

    assert counts == {
        "stopped_deployments": 1,
        "cancelled_builds": 1,
        "cancelled_training_jobs": 1,
        "cancelled_drift_runs": 1,
    }
    assert stopped_deployments == [active_deployment.pk]
    assert stopped_deployment.pk not in stopped_deployments
    assert cancelled_builds == [active_build.pk]
    assert cancelled_jobs == [active_job.pk]
    assert cancelled_runs == [active_run.pk]


@pytest.mark.django_db
@override_settings(ACCOUNT_DELETION_RETENTION_DAYS=15)
def test_purge_user_account_respects_retention_days():
    User = get_user_model()
    user = User.objects.create_user("recent-del@example.com", "password123")
    user.soft_delete()
    User.objects.filter(pk=user.pk).update(deleted_at=timezone.now() - timedelta(days=10))
    storage = FakeStorage()

    outcome = purge_user_account(user.pk, storage=storage)

    assert outcome == "not_expired"
    assert User.objects.filter(pk=user.pk).exists()
    assert storage.prefixes == []


@pytest.mark.django_db
@override_settings(ACCOUNT_DELETION_RETENTION_DAYS=30)
def test_purge_user_account_stages_projects_jobs_workspaces_then_s3_and_user(monkeypatch):
    User = get_user_model()
    user = User.objects.create_user("expired-del@example.com", "password123")
    other_user = User.objects.create_user("active-other@example.com", "password123")
    user.soft_delete()
    User.objects.filter(pk=user.pk).update(deleted_at=timezone.now() - timedelta(days=31))
    tenant_id = user.tenant_id

    project = ModelProject.objects.create(owner=user, name="Expired Project")
    workspace = TrainingWorkspace.objects.create(owner=user)
    job = training_job(
        owner=user,
        workspace=workspace,
        model_flavor="sklearn",
        vcpu=2,
        memory_mb=4096,
        max_runtime_seconds=3600,
        status="completed",
    )
    storage = FakeStorage()

    requested_projects = []
    requested_jobs = []
    requested_workspaces = []

    monkeypatch.setattr(
        "apps.catalog.projects.deletion.request_project_deletion",
        lambda item: requested_projects.append(item.pk),
    )
    monkeypatch.setattr(
        "apps.training.jobs.lifecycle.request_job_deletion",
        lambda item: requested_jobs.append(item.pk),
    )
    monkeypatch.setattr(
        "apps.training.workspace.lifecycle.request_workspace_deletion",
        lambda item: requested_workspaces.append(item.pk),
    )

    assert purge_user_account(user.pk, storage=storage) == "waiting_projects"
    user.refresh_from_db()
    assert user.purge_started_at is not None
    assert requested_projects == [project.pk]
    assert requested_jobs == []
    assert requested_workspaces == []
    assert storage.prefixes == []

    project.delete()
    assert purge_user_account(user.pk, storage=storage) == "waiting_training_jobs"
    assert requested_jobs == [job.pk]
    assert requested_workspaces == []
    assert storage.prefixes == []

    job.delete()
    assert purge_user_account(user.pk, storage=storage) == "waiting_workspaces"
    assert requested_workspaces == [workspace.pk]
    assert storage.prefixes == []

    workspace.delete()
    assert purge_user_account(user.pk, storage=storage) == "purged"
    assert storage.prefixes == [f"users/{tenant_id}/", f"staging/users/{tenant_id}/"]
    assert not User.objects.filter(pk=user.pk).exists()
    assert User.objects.filter(pk=other_user.pk).exists()


@pytest.mark.django_db
@override_settings(ACCOUNT_DELETION_RETENTION_DAYS=30, ACCOUNT_DELETION_PURGE_BATCH_SIZE=10)
def test_purge_expired_deleted_accounts_batch_only_processes_expired_users():
    User = get_user_model()
    expired = User.objects.create_user("batch-expired@example.com", "password123")
    expired.soft_delete()
    User.objects.filter(pk=expired.pk).update(deleted_at=timezone.now() - timedelta(days=31))

    recent = User.objects.create_user("batch-recent@example.com", "password123")
    recent.soft_delete()
    User.objects.filter(pk=recent.pk).update(deleted_at=timezone.now() - timedelta(days=5))

    active = User.objects.create_user("batch-active@example.com", "password123")

    storage = FakeStorage()
    summary = purge_expired_deleted_accounts_batch(storage=storage)

    assert summary["purged"] == 1
    assert summary["errors"] == 0
    assert not User.objects.filter(pk=expired.pk).exists()
    assert User.objects.filter(pk=recent.pk).exists()
    assert User.objects.filter(pk=active.pk).exists()


@pytest.mark.django_db
def test_purge_requeues_failed_training_job(expired_account, django_capture_on_commit_callbacks, monkeypatch):
    job = training_job(
        owner=expired_account,
        status="completed",
        deletion_requested_at=timezone.now() - timedelta(days=1),
        deletion_error="Temporary storage failure",
    )
    in_progress = training_job(
        owner=expired_account, status="completed", deletion_requested_at=timezone.now()
    )
    enqueued = []
    monkeypatch.setattr(
        "apps.observability.execution.leases.enqueue_safely", lambda row, task: enqueued.append(row.pk)
    )
    storage = FakeStorage()

    with django_capture_on_commit_callbacks(execute=True):
        summary = purge_expired_deleted_accounts_batch(storage=storage)

    assert summary["waiting_training_jobs"] == 1
    assert enqueued == [job.pk]
    job.refresh_from_db()
    assert job.deletion_error == ""
    original_request = in_progress.deletion_requested_at
    in_progress.refresh_from_db()
    assert in_progress.deletion_requested_at == original_request
    assert storage.prefixes == []


@pytest.mark.django_db
@override_settings(ACCOUNT_DELETION_PURGE_INTERVAL_SECONDS=60)
def test_blocked_purge_does_not_starve_newer_accounts_at_next_tick(expired_account, monkeypatch):
    ModelProject.objects.create(owner=expired_account, name="Blocked Project", deletion_state="deleting")
    later = get_user_model().objects.create_user(
        "later-purge@example.com", is_active=False, deleted_at=expired_account.deleted_at + timedelta(hours=1)
    )
    now = timezone.now()
    monkeypatch.setattr("apps.auth.account.lifecycle.timezone.now", lambda: now)
    storage = FakeStorage()

    assert purge_expired_deleted_accounts_batch(limit=1, storage=storage)["waiting_projects"] == 1
    expired_account.refresh_from_db()
    assert expired_account.purge_next_attempt_at == now + timedelta(seconds=60)

    now += timedelta(seconds=60)
    assert purge_expired_deleted_accounts_batch(limit=1, storage=storage)["purged"] == 1
    assert not type(later).objects.filter(pk=later.pk).exists()
    assert purge_expired_deleted_accounts_batch(limit=1, storage=storage)["waiting_projects"] == 1


@pytest.mark.django_db
@override_settings(ACCOUNT_DELETION_PURGE_INTERVAL_SECONDS=60)
def test_failed_account_purge_waits_until_its_next_attempt(expired_account, monkeypatch):
    class UnavailableStorage:
        def delete_prefix(self, prefix):
            raise TimeoutError("Storage unavailable")

    now = timezone.now()
    monkeypatch.setattr("apps.auth.account.lifecycle.timezone.now", lambda: now)
    assert purge_expired_deleted_accounts_batch(storage=UnavailableStorage())["errors"] == 1
    expired_account.refresh_from_db()
    assert expired_account.purge_next_attempt_at == now + timedelta(seconds=60)

    storage = FakeStorage()
    now += timedelta(seconds=59)
    assert purge_expired_deleted_accounts_batch(storage=storage)["purged"] == 0
    assert storage.prefixes == []
    now += timedelta(seconds=1)
    assert purge_expired_deleted_accounts_batch(storage=storage)["purged"] == 1


@pytest.mark.django_db
def test_profile_put_cannot_overwrite_auth_provider():
    User = get_user_model()
    user = User.objects.create_user("provider-ro@example.com", "password123", auth_provider="password")
    client = APIClient()
    client.force_authenticate(user)

    response = client.put("/api/auth/profile/", {"auth_provider": "google", "full_name": "Updated"}, format="json")
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.auth_provider == "password"
    assert user.full_name == "Updated"


@pytest.mark.django_db
def test_soft_delete_revokes_credentials_clears_cookie_and_is_idempotent(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    from django.conf import settings
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    from apps.access.models import UserAPIKey
    from apps.auth.account.lifecycle import deactivate_user_account
    from apps.auth.sessions.serializers import TenantTokenSerializer
    from apps.mlflow.auth import authenticate_mlflow_request

    User = get_user_model()
    user = User.objects.create_user("revoke-all@example.com", "password123")
    raw_key, key_prefix, key_hash = UserAPIKey.issue()
    api_key = UserAPIKey.objects.create(user=user, name="mlflow-key", key_prefix=key_prefix, key_hash=key_hash)
    TenantTokenSerializer.get_token(user)
    assert OutstandingToken.objects.filter(user=user).count() == 1
    initial_version = user.session_version

    enqueued = []
    monkeypatch.setattr("apps.auth.tasks.stop_user_active_executions.delay", lambda uid: enqueued.append(uid))

    client = APIClient()
    client.force_authenticate(user)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete("/api/auth/profile/delete/")

    assert response.status_code == 204
    cookie_name = settings.AUTH_COOKIE_NAME
    assert cookie_name in response.cookies
    assert response.cookies[cookie_name].value == ""

    user.refresh_from_db()
    api_key.refresh_from_db()
    assert not user.is_active
    assert user.session_version == initial_version + 1
    assert api_key.revoked_at is not None
    assert BlacklistedToken.objects.filter(token__user=user).count() == 1
    assert enqueued == [user.pk]

    # Idempotent repeat call does not emit duplicate task or dead outbox event
    with django_capture_on_commit_callbacks(execute=True):
        deactivate_user_account(user)
    assert enqueued == [user.pk]
    assert not EventOutbox.objects.filter(aggregate_id=user.public_id, event_type="tenant.disabled").exists()

    # MLflow rejects both revoked/inactive user API key and inactive authenticated user
    factory_req = type("Req", (), {"headers": {"Authorization": f"Bearer {raw_key}"}, "user": user})()
    assert authenticate_mlflow_request(factory_req) == (None, None, None, None, None)


@pytest.mark.django_db
def test_run_project_cleanup_skips_storage_migration_during_account_purge(monkeypatch):
    from apps.catalog.projects.deletion import run_project_cleanup

    User = get_user_model()
    user = User.objects.create_user("purge-skip-mig@example.com", "password123")
    user.soft_delete()
    User.objects.filter(pk=user.pk).update(purge_started_at=timezone.now())
    user.refresh_from_db()
    project = ModelProject.objects.create(owner=user, name="Skip Migration", deletion_state="deleting", is_active=False)

    called = []
    monkeypatch.setattr("apps.training.jobs.storage_migration.migrate_project_storage", lambda p: called.append(p.pk))
    monkeypatch.setattr(
        "apps.catalog.projects.deletion.project_cleanup_backend",
        lambda: type("B", (), {"run": lambda self, p, m: {"dispatched": True}})(),
    )
    run_project_cleanup(project)
    assert called == []


@pytest.mark.django_db
def test_deactivate_user_account_invalidates_model_server_caches(monkeypatch, django_capture_on_commit_callbacks):
    from apps.auth.account.lifecycle import deactivate_user_account

    User = get_user_model()
    user = User.objects.create_user("cache-evict@example.com", "password123")
    project = ModelProject.objects.create(owner=user, name="Cache Evict Project")
    version = ModelVersion.objects.create(project=project, version="1")
    build = Build.objects.create(project=project, version=version, flavor="sklearn", status="ready")
    Deployment.objects.create(version=version, build=build, backend="docker", status="succeeded")

    invalidated = []
    monkeypatch.setattr("apps.deployment.serving.model_server_cache.invalidate_model_server_cache", invalidated.append)
    monkeypatch.setattr("apps.auth.tasks.stop_user_active_executions.delay", lambda uid: None)

    with django_capture_on_commit_callbacks(execute=True):
        deactivate_user_account(user)

    assert invalidated == [str(version.public_id)]
