import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models.functions import Coalesce, Now
from django.utils import timezone

from apps.deployment.models import Build
from common.deletion_retry import deletion_cleanup_retry_at
from infrastructure.execution.build_cleanup import stop_build_for_deletion
from infrastructure.images.cleanup import BuildImageCleaner
from infrastructure.images.references import temporary_image_reference
from infrastructure.storage import S3Storage
from infrastructure.storage.paths import build_prefix

logger = logging.getLogger(__name__)


@shared_task(name="apps.deployment.tasks.cleanup_registered_build_storage", acks_late=True, reject_on_worker_lost=True)
def cleanup_registered_build_storage(build_id):
    from apps.registry.models import ModelArtifact

    with transaction.atomic():
        now = timezone.now()
        build = (
            Build.objects.select_for_update(of=("self",))
            .select_related("project__owner")
            .filter(
                public_id=build_id,
                status="ready",
                deletion_state="active",
                project__deletion_state="active",
                registered_storage_cleanup_due_at__lte=now,
            )
            .first()
        )
        if not build:
            return "not_due"
        # The next scan can retry after this lease if the worker or storage fails.
        retry_at = deletion_cleanup_retry_at(now)
        build.registered_storage_cleanup_due_at = retry_at
        build.save(update_fields=["registered_storage_cleanup_due_at"])

    storage = S3Storage()
    prefix = f"{build_prefix(build.project.owner.tenant_id, build.project.public_id, build.public_id)}/"
    if ModelArtifact.objects.filter(uri__startswith=f"s3://{storage.bucket}/{prefix}").exists():
        raise RuntimeError(f"Build {build.public_id} storage is still referenced by a model version.")
    storage.delete_prefix(prefix)

    with transaction.atomic():
        updated = Build.objects.filter(pk=build.pk, registered_storage_cleanup_due_at=retry_at).update(
            package_uri="", registered_storage_cleanup_due_at=None
        )
        if updated:
            build.input_assets.update(s3_uri="", purged_at=Coalesce("purged_at", Now()))
    return "purged"


@shared_task(
    name="apps.deployment.tasks.cleanup_failed_build_artifacts",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    reject_on_worker_lost=True,
)
def cleanup_failed_build_artifacts(self, build_id, delete_image=False):
    build = (
        Build.objects.select_related("project", "project__owner")
        .prefetch_related("input_assets")
        .filter(public_id=build_id)
        .first()
    )
    if not build:
        return "not_found"
    if build.status not in {"failed", "cancelled"} or build.deletion_state != "active" or build.version_id:
        return "retained"
    if build.backend == "docker" and build.next_execution_check_at:
        # The watcher must stop/observe the runner before outputs are removed.
        return "waiting-for-execution"
    if build.backend == "argo":
        retry_at = timezone.now() + timedelta(seconds=max(1, settings.DELETION_RECONCILE_GRACE_SECONDS))
        Build.objects.filter(pk=build.pk).update(next_execution_check_at=retry_at)
        if stop_build_for_deletion(build) is False:
            return "waiting-for-execution"
        if (
            delete_image
            or build.started_at
            or build.execution_deadline_at
            or build.execution_completed_at
            or build.image_uri
        ):
            build.image_uri = temporary_image_reference(
                build.project.public_id,
                build.public_id,
                registry=settings.HARBOR_REGISTRY_URL,
                registry_project=settings.HARBOR_USER_PROJECT,
            )
            BuildImageCleaner().delete(build)
    elif delete_image and build.image_uri:
        BuildImageCleaner().delete(build)
    storage = S3Storage()
    prefix = build_prefix(build.project.owner.tenant_id, build.project.public_id, build.public_id)
    storage.delete_prefix(f"{prefix}/")
    build.input_assets.update(s3_uri="", purged_at=timezone.now())
    if build.backend == "argo":
        Build.objects.filter(pk=build.pk, next_execution_check_at=retry_at).update(next_execution_check_at=None)
    return "purged"


def _check_build_deletable(build):
    if build.version_id or build.registration_status in {"registering", "registered"} or build.deployments.exists():
        raise RuntimeError("Registered builds must be retained.")


# reject_on_worker_lost: with acks_late, a worker killed mid-task would otherwise acknowledge the
# message and the build would stay "deleting" with nothing left to finish it. Every step is
# idempotent, so a redelivery is safe.
@shared_task(name="apps.deployment.tasks.delete_build", bind=True, max_retries=5, reject_on_worker_lost=True)
def delete_build(self, build_id):
    try:
        return cleanup_build_for_deletion(build_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=min(10 * 2**self.request.retries, 120)) from exc


def cleanup_build_for_deletion(build_id):
    """Keep the tombstone until external cleanup succeeds; repeated DELETE retries it.

    The runtime, image and object-storage cleanup is slow external I/O, so no lock is held
    while it runs: the build is validated under the lock, cleaned with no lock, and its row is
    removed in a second short transaction that validates again.
    """
    from apps.catalog.models import ModelProject

    candidate = Build.objects.filter(public_id=build_id).first()
    if not candidate:
        return "deleted"
    try:
        with transaction.atomic():
            ModelProject.objects.select_for_update().get(pk=candidate.project_id)
            build = (
                Build.objects.select_for_update(of=("self",))
                .select_related("project__owner")
                .filter(public_id=build_id)
                .first()
            )
            if not build:
                return "deleted"
            if build.deletion_state == "active":
                return "retained"
            _check_build_deletable(build)
            prefix = build_prefix(build.project.owner.tenant_id, build.project.public_id, build.public_id)
            prefix = f"{prefix.rstrip('/')}/"

        # A fresh object: the runner may have reported its end while the lock was released.
        build = Build.objects.select_related("project").filter(pk=build.pk).first()
        if not build:
            return "deleted"
        if stop_build_for_deletion(build) is False:
            return "waiting-for-execution"
        # Use the server-generated build tag even if the runner failed before
        # reporting image_uri. Never delete a caller-supplied repository/digest.
        build.image_uri = temporary_image_reference(
            build.project.public_id,
            build.public_id,
            registry=settings.HARBOR_REGISTRY_URL if build.backend == "argo" else "",
            registry_project=settings.HARBOR_USER_PROJECT,
        )
        BuildImageCleaner().delete(build)
        S3Storage().delete_prefix(prefix)

        with transaction.atomic():
            ModelProject.objects.select_for_update().get(pk=candidate.project_id)
            build = Build.objects.select_for_update(of=("self",)).filter(pk=build.pk).first()
            if not build:
                return "deleted"
            if build.deletion_state == "active":
                return "retained"
            _check_build_deletable(build)
            build.delete()
        return "deleted"
    except Exception as exc:
        Build.objects.filter(public_id=build_id).update(
            deletion_state="delete_failed", deletion_error="Build cleanup failed; retry Delete or check worker logs."
        )
        logger.warning("Build cleanup failed for %s (%s).", build_id, type(exc).__name__)
        raise
