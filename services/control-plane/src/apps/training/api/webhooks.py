from django.conf import settings
from django.db import transaction
from django.utils import timezone
from infrastructure.storage import S3Storage
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.training.models import TrainingJob, TrainingJobEvent, TrainingOutput
from apps.training.services.capabilities import capability_for_token
from apps.training.services.logs import append_training_log
from apps.training.services.storage_scope import validate_training_uri


def _bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    return authorization[7:] if authorization.startswith("Bearer ") else ""


def _terminal_status(workflow_status):
    normalized = str(workflow_status or "").lower()
    if normalized in {"success", "succeeded", "completed"}:
        return "completed"
    if normalized in {"failed", "error"}:
        return "failed"
    if normalized in {"cancelled", "canceled", "stopped", "terminated"}:
        return "cancelled"
    return None


class TrainingJobWebhookEndpoint(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request, job_id):
        key = request.headers.get("Idempotency-Key") or str(request.data.get("idempotency_key", ""))
        with transaction.atomic():
            try:
                job = TrainingJob.objects.select_for_update().get(public_id=job_id)
            except TrainingJob.DoesNotExist:
                return Response({"status": "deleted", "ignored": True})
            capability = capability_for_token(
                job=job,
                purpose="trusted_reporter",
                token=_bearer_token(request),
            )
            if not capability:
                return Response({"detail": "Invalid training reporter capability."}, status=status.HTTP_403_FORBIDDEN)
            if key and TrainingJobEvent.objects.filter(job=job, idempotency_key=key).exists():
                return Response({"status": job.status, "duplicate": True})
            if capability.consumed_at:
                return Response(
                    {"detail": "Training reporter capability was already consumed."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            status_value = _terminal_status(request.data.get("workflow_status"))
            if not status_value:
                return Response(
                    {"detail": "A terminal workflow_status is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if job.status in {"cancelling", "completed", "failed", "cancelled"} or job.deletion_requested_at:
                capability.consumed_at = timezone.now()
                capability.save(update_fields=["consumed_at"])
                return Response({"status": job.status, "ignored": True})
            if status_value == "completed":
                job.mark_finished("completed")
                TrainingOutput.objects.update_or_create(
                    job=job,
                    relative_path="model.tar.gz",
                    defaults={"kind": "model", "s3_uri": job.output_uri},
                )
            elif status_value == "failed":
                job.mark_finished("failed")
                job.error_message = "Training workflow failed."
            else:
                job.mark_finished("cancelled")
            capability.consumed_at = timezone.now()
            capability.save(update_fields=["consumed_at"])
            job.save(update_fields=["status", "completed_at", "runtime_seconds", "error_message", "updated_at"])
            TrainingJobEvent.objects.create(
                job=job,
                event_type="trusted_reporter",
                message=f"Training status changed to {job.status}.",
                metadata={"workflow_status": str(request.data.get("workflow_status", ""))},
                idempotency_key=key,
            )
        append_training_log(job.public_id, f"[SYSTEM] Training reached terminal status: {job.status}.")
        return Response({"status": job.status})


class TrainingCancellationWebhookEndpoint(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request, job_id):
        from apps.training.tasks import confirm_training_cancellation

        key = request.headers.get("Idempotency-Key") or str(
            request.data.get("idempotency_key", "")
        )
        workflow_status = str(request.data.get("workflow_status", "")).lower()
        with transaction.atomic():
            try:
                job = TrainingJob.objects.select_for_update().get(public_id=job_id)
            except TrainingJob.DoesNotExist:
                return Response({"status": "deleted", "duplicate": True})
            capability = capability_for_token(
                job=job,
                purpose="cancel_reporter",
                token=_bearer_token(request),
            )
            if not capability:
                return Response(
                    {"detail": "Invalid cancellation reporter capability."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if key and TrainingJobEvent.objects.filter(
                job=job, idempotency_key=key
            ).exists():
                return Response({"status": job.status, "duplicate": True})
            if capability.consumed_at:
                return Response(
                    {"detail": "Cancellation reporter capability was already consumed."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if workflow_status not in {"succeeded", "success", "completed", "failed", "error"}:
                return Response(
                    {"detail": "A terminal workflow_status is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            capability.consumed_at = timezone.now()
            capability.save(update_fields=["consumed_at"])
            succeeded = workflow_status in {"succeeded", "success", "completed"}
            if not succeeded:
                job.deletion_error = "Kubernetes training cancellation workflow failed."
                job.save(update_fields=["deletion_error", "updated_at"])
            TrainingJobEvent.objects.create(
                job=job,
                event_type="cancellation_confirmed" if succeeded else "cancellation_failed",
                message=(
                    "Kubernetes confirmed that the training runtime was removed."
                    if succeeded
                    else "Kubernetes could not remove the training runtime."
                ),
                metadata={"workflow_status": workflow_status},
                idempotency_key=key,
            )
        if succeeded:
            confirm_training_cancellation(str(job.public_id))
        return Response(
            {
                "status": "cancelled" if succeeded else "cancelling",
                "deletion_error": "" if succeeded else job.deletion_error,
            }
        )


class TrainingOutputUploadURLEndpoint(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request, job_id):
        with transaction.atomic():
            job = TrainingJob.objects.select_for_update().select_related("project__owner").get(public_id=job_id)
            capability = capability_for_token(
                job=job,
                purpose="output_upload",
                token=_bearer_token(request),
            )
            if not capability or capability.consumed_at:
                return Response({"detail": "Invalid training output capability."}, status=status.HTTP_403_FORBIDDEN)
            storage = S3Storage()
            validate_training_uri(job, storage.bucket, "output", job.output_uri)
            upload_url = storage.presigned_put(
                job.output_uri,
                settings.TRAINING_PRESIGNED_URL_TTL_SECONDS,
                "application/gzip",
            )
            capability.consumed_at = timezone.now()
            capability.save(update_fields=["consumed_at"])
        return Response(
            {
                "upload_url": upload_url,
                "expires_in": settings.TRAINING_PRESIGNED_URL_TTL_SECONDS,
            }
        )
