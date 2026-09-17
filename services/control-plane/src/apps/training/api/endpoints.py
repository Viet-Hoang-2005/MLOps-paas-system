from common.api.exceptions import ServiceUnavailable
from django.conf import settings
from django.db.models import Prefetch
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.deployment.models import Build
from apps.deployment.services.builds import request_training_build
from apps.observability.services.lifecycle import events_for_aggregate
from apps.training.selectors import job_for_user, jobs_for_user
from apps.training.services.jobs import (
    cancel_job,
    create_job,
    output_download_url,
    request_job_deletion,
    request_output_purge,
    submit_job,
)
from apps.training.services.logs import training_logs

from .serializers import TrainingBuildSerializer, TrainingJobEventSerializer, TrainingJobSerializer


def require_training_enabled():
    if not settings.TRAINING_ENABLED:
        raise ServiceUnavailable("Training is temporarily unavailable while the platform is being validated.")


class TrainingJobListCreateEndpoint(generics.ListCreateAPIView):
    serializer_class = TrainingJobSerializer

    def get_queryset(self):
        return jobs_for_user(self.request.user).prefetch_related(
            "outputs",
            Prefetch(
                "builds",
                queryset=Build.objects.select_related("version").prefetch_related("version__deployments"),
            ),
        )

    def perform_create(self, serializer):
        require_training_enabled()
        project = serializer.validated_data.pop("project")
        serializer.instance = create_job(project=project, validated_data=serializer.validated_data)


class TrainingJobDetailEndpoint(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TrainingJobSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "job_id"

    def get_queryset(self):
        return jobs_for_user(self.request.user).prefetch_related(
            "outputs",
            Prefetch(
                "builds",
                queryset=Build.objects.select_related("version").prefetch_related("version__deployments"),
            ),
        )

    def delete(self, request, *args, **kwargs):
        job = request_job_deletion(self.get_object())
        return Response(
            {
                "id": str(job.public_id),
                "deletion_pending": True,
                "status": job.status,
                "deletion_requested_at": job.deletion_requested_at,
                "deletion_error": job.deletion_error,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class TrainingJobSubmitEndpoint(APIView):
    def post(self, request, job_id):
        require_training_enabled()
        job = submit_job(job_for_user(request.user, job_id))
        return Response(TrainingJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class TrainingJobCancelEndpoint(APIView):
    def post(self, request, job_id):
        job = cancel_job(job_for_user(request.user, job_id))
        return Response(TrainingJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class TrainingJobEventsEndpoint(APIView):
    def get(self, request, job_id):
        job = job_for_user(request.user, job_id)
        return Response(
            TrainingJobEventSerializer(
                events_for_aggregate(aggregate_type="training_job", aggregate_id=job.public_id), many=True
            ).data
        )


class TrainingJobLogsEndpoint(APIView):
    def get(self, request, job_id):
        try:
            offset = int(request.query_params.get("offset", "0"))
        except (TypeError, ValueError):
            offset = -1
        if offset < 0:
            return Response(
                {"detail": "offset must be a non-negative integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        job = job_for_user(request.user, job_id)
        logs, next_offset = training_logs(job, offset)
        return Response(
            {
                "training_job_id": str(job.public_id),
                "logs": logs,
                "next_offset": next_offset,
                "status": job.status,
                "error_message": job.error_message,
            }
        )


class TrainingJobDownloadEndpoint(APIView):
    def get(self, request, job_id):
        job = job_for_user(request.user, job_id)
        return Response({"download_url": output_download_url(job)})


class TrainingJobBuildEndpoint(APIView):
    def post(self, request, job_id):
        build, created = request_training_build(
            job=job_for_user(request.user, job_id),
            backend=settings.BUILD_BACKEND,
        )
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(TrainingBuildSerializer(build).data, status=response_status)


class TrainingJobOutputsEndpoint(APIView):
    def delete(self, request, job_id):
        job = request_output_purge(job_for_user(request.user, job_id))
        return Response(TrainingJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class TrainingRuntimeCapabilitiesEndpoint(APIView):
    def get(self, request):
        if not settings.TRAINING_ENABLED:
            return Response(
                {
                    "enabled": False,
                    "backend": settings.TRAINING_BACKEND,
                    "cpu_profiles": [],
                    "accelerators": [],
                }
            )
        accelerators = [{"type": "none", "counts": [0]}]
        if settings.TRAINING_GPU_ENABLED:
            accelerators.append(
                {"type": "gpu", "counts": list(settings.TRAINING_GPU_COUNTS or (1,))}
            )
        return Response(
            {
                "enabled": True,
                "backend": settings.TRAINING_BACKEND,
                "cpu_profiles": [
                    {"id": "small", "vcpu": 1, "memory_mb": 2048},
                    {"id": "medium", "vcpu": 2, "memory_mb": 4096},
                    {"id": "large", "vcpu": 4, "memory_mb": 8192},
                ],
                "accelerators": accelerators,
            }
        )
