from django.conf import settings
from django.db.models import Prefetch
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.deployment.builds.serializers import BuildSerializer
from apps.deployment.builds.submission import request_training_build
from apps.deployment.models import Build
from apps.observability.lifecycle import events_for_aggregate
from apps.training.jobs.lifecycle import cancel_job, request_job_deletion
from apps.training.jobs.logs import training_logs
from apps.training.jobs.selectors import job_for_user, jobs_for_user
from apps.training.jobs.serializers import (
    TrainingJobBuildRequestSerializer,
    TrainingJobEventSerializer,
    TrainingJobProjectRequestSerializer,
    TrainingJobSerializer,
)
from common.api.exceptions import Conflict, ServiceUnavailable
from infrastructure.telemetry.runtime_logs import runtime_log_page


def require_training_enabled():
    if not settings.TRAINING_ENABLED:
        raise ServiceUnavailable("Training is temporarily unavailable while the platform is being validated.")


class TrainingJobListEndpoint(generics.ListAPIView):
    serializer_class = TrainingJobSerializer

    def get_queryset(self):
        return jobs_for_user(self.request.user).prefetch_related(
            "outputs",
            Prefetch(
                "builds",
                queryset=Build.objects.select_related("version").prefetch_related("version__deployments"),
            ),
        )


class TrainingJobDetailEndpoint(generics.RetrieveDestroyAPIView):
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

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "include_workspace": True}

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


class TrainingJobProjectEndpoint(APIView):
    def post(self, request, job_id):
        from apps.training.jobs.project_assignment import assign_project

        job = job_for_user(request.user, job_id)
        payload = {key: value for key, value in request.data.items() if key not in request.FILES}
        import json

        for field in ("new_project", "artifacts"):
            if isinstance(payload.get(field), str):
                try:
                    payload[field] = json.loads(payload[field])
                except ValueError:
                    raise ValidationError({field: "Invalid JSON."}) from None
        serializer = TrainingJobProjectRequestSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        job = assign_project(job=job, actor=request.user, data=serializer.validated_data, files=request.FILES)
        return Response(TrainingJobSerializer(job).data)


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
        job = job_for_user(request.user, job_id)
        page = runtime_log_page(request, job, "training", training_logs)
        return Response(
            {
                "training_job_id": str(job.public_id),
                **page,
                "status": job.status,
                "error_message": job.error_message,
            }
        )


class TrainingJobInputEndpoint(APIView):
    def get(self, request, job_id):
        from apps.training.jobs.snapshots import input_snapshot

        return Response(
            input_snapshot(
                job_for_user(request.user, job_id),
                path=request.query_params.get("path"),
                download=request.query_params.get("download") == "1",
            )
        )


class TrainingJobBuildEndpoint(APIView):
    def post(self, request, job_id):
        job = job_for_user(request.user, job_id)
        if not job.project_id:
            raise Conflict("Assign this training job to a project before building a model.")
        request_serializer = TrainingJobBuildRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        build, created = request_training_build(
            job=job,
            output_revision=request_serializer.validated_data["output_revision"],
            backend=settings.BUILD_BACKEND,
        )
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(BuildSerializer(build).data, status=response_status)
