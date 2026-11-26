from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.training.models import TrainingWorkspace
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def cleanup_preparation(job_id, token, prefix=None):
    from apps.training.models import TrainingJob
    from .storage_scope import training_prefix_for

    job = TrainingJob.objects.filter(public_id=job_id).first()
    if job and (job.submitted_at or str(job.submission_token) == token):
        return
    if job:
        prefix = f"{training_prefix_for(job)}/input/submissions/{token}/"
    if prefix and prefix.startswith("users/") and prefix.endswith(f"/training/jobs/{job_id}/input/submissions/{token}/"):
        S3Storage().delete_prefix(prefix)


def request_workspace_deletion(workspace):
    with transaction.atomic():
        row = TrainingWorkspace.objects.select_for_update().get(pk=workspace.pk)
        list(row.jobs.select_for_update().values_list("pk", flat=True))
        if row.jobs.exists():
            raise Conflict(
                {
                    "jobs": [str(value) for value in row.jobs.values_list("public_id", flat=True)],
                    "detail": "Delete all training jobs in this workspace before deleting the workspace.",
                }
            )
        row.deletion_requested_at = timezone.now()
        row.deletion_error = ""
        row.save(update_fields=["deletion_requested_at", "deletion_error", "updated_at"])
        transaction.on_commit(lambda: cleanup_workspace.delay(str(row.public_id)))


@shared_task(bind=True, max_retries=None)
def cleanup_workspace(self, workspace_id):
    row = TrainingWorkspace.objects.filter(public_id=workspace_id, deletion_requested_at__isnull=False).first()
    if not row:
        return
    if row.jobs.exists():
        errors = list(row.jobs.exclude(deletion_error="").values_list("deletion_error", flat=True))
        if errors:
            TrainingWorkspace.objects.filter(pk=row.pk).update(deletion_error="; ".join(errors)[:12000])
            return
        raise self.retry(countdown=15)
    try:
        S3Storage().delete_prefix(f"users/{row.owner.tenant_id}/training/workspaces/{row.public_id}/")
        row.delete()
    except Exception as exc:
        TrainingWorkspace.objects.filter(pk=row.pk).update(deletion_error=str(exc)[:12000])
        raise self.retry(exc=exc, countdown=30)
