from celery import shared_task
from django.db import transaction

from apps.training.jobs.storage_scope import training_prefix_for
from common.telemetry.logging import record_transition
from infrastructure.storage import S3Storage


@shared_task(
    name="apps.training.tasks.purge_training_job_outputs",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    reject_on_worker_lost=True,
)
def purge_training_job_outputs(self, job_id):
    from apps.observability.lifecycle import record_training_event

    from apps.training.jobs.models import TrainingJob

    job = TrainingJob.objects.select_related("project", "project__owner").get(public_id=job_id)
    storage = S3Storage()
    prefix = training_prefix_for(job)
    storage.delete_prefix(f"{prefix}/output/")
    storage.delete_prefix(f"{prefix}/mlflow/")
    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().get(pk=job.pk)
        job.outputs.all().delete()
        record_training_event(
            job=job,
            event_type="outputs_purged",
            message="Training outputs were deleted.",
        )
        record_transition(job, job.status, phase="outputs_purged")
    return "purged"
