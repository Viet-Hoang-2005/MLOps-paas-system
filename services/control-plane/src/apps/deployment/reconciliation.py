import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db.models import F, Q
from django.utils import timezone

from apps.deployment.builds.cleanup import (
    cleanup_failed_build_artifacts,
    cleanup_registered_build_storage,
    delete_build,
)
from apps.deployment.models import Build
from common.deletion_retry import deletion_cleanup_retry_at

logger = logging.getLogger(__name__)


def _dispatch_once(kind, public_id, task, grace):
    # A task that keeps failing is retried at most once per grace period, not on every scan.
    if cache.add(f"deletion-reconcile:{kind}:{public_id}", 1, timeout=grace):
        task.delay(str(public_id))
        return 1
    return 0


def _dispatch_due_cleanup(rows, task, now, limit):
    # Pending rows from before the deadline was introduced are immediately eligible.
    due = Q(deletion_cleanup_due_at__isnull=True) | Q(deletion_cleanup_due_at__lte=now)
    candidates = list(
        rows.filter(due)
        .order_by(F("deletion_cleanup_due_at").asc(nulls_first=True), "pk")
        .values_list("pk", "public_id")[:limit]
    )
    pending = rows.model.objects.filter(deletion_requested=True).filter(due)
    dispatched = 0
    for pk, public_id in candidates:
        # Advance before publishing so a failed publish or lost message does not monopolize the next batch.
        if pending.filter(pk=pk).update(deletion_cleanup_due_at=deletion_cleanup_retry_at(now)):
            try:
                task.delay(str(public_id))
                dispatched += 1
            except Exception:
                logger.warning("Failed to dispatch cleanup for %s %s.", rows.model.__name__, public_id, exc_info=True)
    return dispatched


@shared_task(
    name="apps.deployment.tasks.reconcile_stalled_deletions",
    ignore_result=True,
    expires=120,
    soft_time_limit=100,
    time_limit=110,
)
def reconcile_stalled_deletions():
    """Re-dispatch unfinished storage cleanups and deletions.

    Deleting a build, project or training job is first recorded in the database and then
    carried out by a queued task. If that task is lost (broker or worker down between the
    commit and the enqueue, or the retries ran out) nothing else would ever finish it, and
    the resource would stay in ``deleting`` forever. A deletion that is still recorded as in
    progress after the grace period gets its task enqueued again; the tasks are idempotent.
    ``delete_failed`` stays user-driven: repeating Delete is the explicit retry.
    """
    from apps.catalog.models import ModelProject
    from apps.catalog.projects.tasks import execute_project_deletion
    from apps.drift.models import DriftMonitor
    from apps.drift.monitors.tasks import cleanup_drift_monitor_task
    from apps.registry.models import ModelVersion
    from apps.registry.versions.tasks import cleanup_model_version
    from apps.training.jobs.models import TrainingJob
    from apps.training.jobs.tasks import delete_training_job

    grace = settings.DELETION_RECONCILE_GRACE_SECONDS
    limit = settings.DELETION_RECONCILE_BATCH_SIZE
    now = timezone.now()
    cutoff = now - timedelta(seconds=grace)
    dispatched = 0
    stale_builds = Build.objects.filter(deletion_state="deleting", updated_at__lt=cutoff).order_by("updated_at")
    for public_id in stale_builds.values_list("public_id", flat=True)[:limit]:
        dispatched += _dispatch_once("build", public_id, delete_build, grace)
    registered_builds = Build.objects.filter(
        status="ready",
        deletion_state="active",
        project__deletion_state="active",
        registered_storage_cleanup_due_at__lte=now,
    ).order_by("registered_storage_cleanup_due_at", "pk")
    for public_id in registered_builds.values_list("public_id", flat=True)[:limit]:
        dispatched += _dispatch_once("registered-build-storage", public_id, cleanup_registered_build_storage, grace)
    argo_builds = Build.objects.filter(
        backend="argo",
        status__in=("failed", "cancelled"),
        version__isnull=True,
        deletion_state="active",
        project__deletion_state="active",
        next_execution_check_at__lte=timezone.now(),
    ).order_by("next_execution_check_at", "pk")
    for public_id in argo_builds.values_list("public_id", flat=True)[:limit]:
        dispatched += _dispatch_once("argo-build-cleanup", public_id, cleanup_failed_build_artifacts, grace)
    stale_projects = ModelProject.objects.filter(deletion_state="deleting", updated_at__lt=cutoff).order_by(
        "updated_at"
    )
    for public_id in stale_projects.values_list("public_id", flat=True)[:limit]:
        dispatched += _dispatch_once("project", public_id, execute_project_deletion, grace)
    stale_jobs = TrainingJob.objects.filter(deletion_requested_at__lt=cutoff, deletion_error="").order_by(
        "deletion_requested_at"
    )
    for public_id in stale_jobs.values_list("public_id", flat=True)[:limit]:
        dispatched += _dispatch_once("training-job", public_id, delete_training_job, grace)
    stale_versions = ModelVersion.objects.filter(deletion_requested=True, project__deletion_state="active")
    dispatched += _dispatch_due_cleanup(stale_versions, cleanup_model_version, now, limit)
    stale_monitors = DriftMonitor.objects.filter(
        deletion_requested=True, version__deletion_requested=False, version__project__deletion_state="active"
    )
    dispatched += _dispatch_due_cleanup(stale_monitors, cleanup_drift_monitor_task, now, limit)
    if dispatched:
        logger.warning("Re-dispatched %s pending cleanup or deletion task(s).", dispatched)
    return dispatched
