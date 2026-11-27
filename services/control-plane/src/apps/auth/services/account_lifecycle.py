import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.auth.models import CustomUser
from apps.observability.services.outbox import enqueue_event
from infrastructure.storage.s3 import S3Storage

logger = logging.getLogger(__name__)


def deactivate_user_account(user):
    """Soft-delete the user, emit tenant.disabled, and enqueue runtime cleanup."""
    from apps.auth.tasks import stop_user_active_executions

    with transaction.atomic():
        user.soft_delete()
        enqueue_event(
            topic="identity.events",
            aggregate_type="user",
            aggregate_id=user.public_id,
            event_type="tenant.disabled",
            payload={"user_id": str(user.public_id), "tenant_id": user.tenant_id},
        )
        transaction.on_commit(lambda user_id=user.pk: stop_user_active_executions.delay(user_id))


def stop_user_active_runtimes(user_id):
    """Stop running deployments and cancel active builds, training jobs, and drift runs."""
    user = CustomUser.objects.filter(pk=user_id, is_active=False, deleted_at__isnull=False).first()
    counts = {
        "stopped_deployments": 0,
        "cancelled_builds": 0,
        "cancelled_training_jobs": 0,
        "cancelled_drift_runs": 0,
    }
    if user is None:
        return counts

    from apps.deployment.models import Build, Deployment
    from apps.deployment.services import builds as build_service
    from apps.deployment.services import deployments as deployment_service
    from apps.deployment.tasks import STOP_CLAIMABLE
    from apps.drift.models import DriftRun
    from apps.drift.services import runs as drift_run_service
    from apps.training.models import TrainingJob
    from apps.training.services import jobs as training_job_service

    for deployment in Deployment.objects.filter(version__project__owner=user, status__in=STOP_CLAIMABLE):
        try:
            deployment_service.request_stop(deployment)
            counts["stopped_deployments"] += 1
        except Exception:
            logger.warning("Failed to stop deployment %s for soft-deleted user %s.", deployment.public_id, user.public_id, exc_info=True)

    for build in Build.objects.filter(project__owner=user, status__in={"pending", "queued", "building"}):
        try:
            build_service.request_cancel(build)
            counts["cancelled_builds"] += 1
        except Exception:
            logger.warning("Failed to cancel build %s for soft-deleted user %s.", build.public_id, user.public_id, exc_info=True)

    for job in TrainingJob.objects.filter(owner=user, status__in=training_job_service.ACTIVE_STATUSES):
        try:
            training_job_service.cancel_job(job)
            counts["cancelled_training_jobs"] += 1
        except Exception:
            logger.warning("Failed to cancel training job %s for soft-deleted user %s.", job.public_id, user.public_id, exc_info=True)

    for run in DriftRun.objects.filter(monitor__version__project__owner=user, status__in={"pending", "queued", "running"}):
        try:
            drift_run_service.request_cancel(run)
            counts["cancelled_drift_runs"] += 1
        except Exception:
            logger.warning("Failed to cancel drift run %s for soft-deleted user %s.", run.public_id, user.public_id, exc_info=True)

    return counts


def _retention_cutoff(now):
    retention_days = max(0, int(getattr(settings, "ACCOUNT_DELETION_RETENTION_DAYS", 30)))
    return now - timedelta(days=retention_days)


def purge_user_account(user_id, *, storage=None, scheduled=False):
    """Delete an expired soft-deleted account and all remaining resources in dependency order."""
    with transaction.atomic():
        user = (
            CustomUser.objects.select_for_update().filter(pk=user_id, is_active=False, deleted_at__isnull=False).first()
        )
        if user is None:
            return "missing"
        now = timezone.now()
        if user.deleted_at > _retention_cutoff(now):
            return "not_expired"
        if scheduled and user.purge_next_attempt_at and user.purge_next_attempt_at > now:
            return "not_due"
        # Persist the next attempt before external work so another batch can advance even
        # if this worker fails or loses its message partway through the purge.
        user.purge_started_at = user.purge_started_at or now
        if scheduled:
            delay = max(1, settings.ACCOUNT_DELETION_PURGE_INTERVAL_SECONDS)
            user.purge_next_attempt_at = now + timedelta(seconds=delay)
        user.save(update_fields=["purge_started_at", "purge_next_attempt_at"])

    from apps.catalog.models import ModelProject
    from apps.catalog.services.deletion import request_project_deletion
    from apps.training.models import TrainingJob, TrainingWorkspace
    from apps.training.services import jobs as training_job_service
    from apps.training.services import workspace_lifecycle

    projects = list(ModelProject.objects.filter(owner=user))
    if projects:
        for project in projects:
            if project.deletion_state != "deleting":
                try:
                    request_project_deletion(project)
                except Exception:
                    logger.warning("Failed to request deletion for project %s of user %s.", project.public_id, user.public_id, exc_info=True)
        return "waiting_projects"

    jobs = list(TrainingJob.objects.filter(owner=user))
    if jobs:
        for job in jobs:
            if job.deletion_requested_at is None or job.deletion_error:
                try:
                    training_job_service.request_job_deletion(job)
                except Exception:
                    logger.warning("Failed to request deletion for training job %s of user %s.", job.public_id, user.public_id, exc_info=True)
        return "waiting_training_jobs"

    workspaces = list(TrainingWorkspace.objects.filter(owner=user))
    if workspaces:
        for workspace in workspaces:
            try:
                workspace_lifecycle.request_workspace_deletion(workspace)
            except Exception:
                logger.warning("Failed to request deletion for workspace %s of user %s.", workspace.public_id, user.public_id, exc_info=True)
        return "waiting_workspaces"

    storage = storage or S3Storage()
    if user.tenant_id:
        storage.delete_prefix(f"users/{user.tenant_id}/")
        storage.delete_prefix(f"staging/users/{user.tenant_id}/")

    user.delete()
    return "purged"


def purge_expired_deleted_accounts_batch(*, limit=None, storage=None):
    """Find expired soft-deleted accounts and advance their staged purge."""
    batch_size = limit or int(getattr(settings, "ACCOUNT_DELETION_PURGE_BATCH_SIZE", 20))
    now = timezone.now()
    due_users = list(
        CustomUser.objects.filter(is_active=False, deleted_at__lte=_retention_cutoff(now))
        .filter(Q(purge_next_attempt_at__isnull=True) | Q(purge_next_attempt_at__lte=now))
        .order_by(Coalesce("purge_next_attempt_at", "deleted_at"), "pk")
        .values_list("pk", "public_id")[:batch_size]
    )
    summary = {
        "purged": 0,
        "waiting_projects": 0,
        "waiting_training_jobs": 0,
        "waiting_workspaces": 0,
        "errors": 0,
    }
    for user_id, public_id in due_users:
        try:
            outcome = purge_user_account(user_id, storage=storage, scheduled=True)
            if outcome in summary:
                summary[outcome] += 1
        except Exception:
            summary["errors"] += 1
            logger.warning("Expired account purge failed for user %s.", public_id, exc_info=True)
    return summary
