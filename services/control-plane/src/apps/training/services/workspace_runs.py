"""Job-scoped, one-use runtime configuration delivery."""
from django.db import transaction
from rest_framework.exceptions import PermissionDenied
from apps.training.models import TrainingJob
from apps.training.services import workspaces


def runtime_configuration(job_id, token):
    from apps.training.services.capabilities import capability_for_token
    with transaction.atomic():
        job = TrainingJob.objects.select_for_update().filter(public_id=job_id).first()
        if job is None:
            raise PermissionDenied("Invalid runtime configuration capability.")
        cap = capability_for_token(job=job, purpose="runtime_config", token=token)
        if not cap or cap.consumed_at or job.status not in {"queued", "running"} or job.execution_stop_requested or job.deletion_requested_at:
            raise PermissionDenied("Invalid runtime configuration capability.")
        if job.project_id and job.project.deletion_state != "active":
            raise PermissionDenied("Training is stopping.")
        values = dict(job.environment_snapshot)
        if job.secret_snapshot:
            cipher = workspaces.cipher()
            values.update({name: cipher.decrypt(value.encode("ascii")).decode("utf-8") for name, value in job.secret_snapshot.items()})
        from django.utils import timezone
        cap.consumed_at = timezone.now()
        cap.save(update_fields=["consumed_at"])
        return {"environment": values, "secret_names": list(job.secret_snapshot)}
