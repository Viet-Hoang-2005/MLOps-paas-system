from django.conf import settings
from django.db import DatabaseError
from django.db.models import Prefetch
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.deployment.models import Build
from apps.deployment.services.builds import request_training_build
from apps.observability.services.lifecycle import events_for_aggregate
from apps.training.api.serializers import TrainingJobBuildRequestSerializer, TrainingJobProjectRequestSerializer
from apps.training.selectors import job_for_user, jobs_for_user
from apps.training.services.jobs import (
    cancel_job,
    create_job,
    request_job_deletion,
    request_output_purge,
    retry_job,
    submit_job,
)
from apps.training.services.logs import training_logs
from apps.training.services.outputs import (
    get_job_reference_preview,
    get_model_output_summary,
    mutate_training_output,
)
from apps.training.services.resources import CPU_PROFILES, GPU_MODELS, runtime_options
from common.api.exceptions import Conflict, ServiceUnavailable
from infrastructure.runtime_logs import runtime_log_page

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

    def create(self, request, *args, **kwargs):
        from .serializers import TrainingDraftSettingsSerializer

        serializer = TrainingDraftSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = create_job(owner=request.user, validated_data=serializer.validated_data)
        return Response(
            TrainingJobSerializer(job, context={"include_workspace": True}).data, status=status.HTTP_201_CREATED
        )


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

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "include_workspace": True}

    def update(self, request, *args, **kwargs):
        from apps.training.services.workspaces import update_workspace

        from .serializers import TrainingDraftSettingsSerializer

        serializer = TrainingDraftSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        revision = values.pop("revision", None)
        job = update_workspace(self.get_object(), revision=revision, changes=values)
        return Response(self.get_serializer(job).data)

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
        from .serializers import TrainingSubmissionSerializer

        serializer = TrainingSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = submit_job(job_for_user(request.user, job_id), **serializer.validated_data)
        return Response(TrainingJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class TrainingJobProjectEndpoint(APIView):
    def post(self, request, job_id):
        from apps.training.services.project_assignment import assign_project

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


class TrainingJobRetryEndpoint(APIView):
    def post(self, request, job_id):
        require_training_enabled()
        from .serializers import TrainingCloneSerializer

        serializer = TrainingCloneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = retry_job(job_for_user(request.user, job_id), **serializer.validated_data)
        return Response(TrainingJobSerializer(job).data, status=status.HTTP_201_CREATED)


class TrainingJobCloneEndpoint(APIView):
    def post(self, request, job_id):
        from apps.training.services.drafts import clone_draft

        from .serializers import TrainingCloneSerializer

        serializer = TrainingCloneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = clone_draft(job_for_user(request.user, job_id), **serializer.validated_data)
        return Response(TrainingJobSerializer(job).data, status=status.HTTP_201_CREATED)


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
        from apps.training.services.snapshots import input_snapshot

        return Response(
            input_snapshot(
                job_for_user(request.user, job_id),
                path=request.query_params.get("path"),
                download=request.query_params.get("download") == "1",
            )
        )


class TrainingOutputDownloadEndpoint(APIView):
    def get(self, request, job_id, output_id):
        from apps.training.services.snapshots import output_download

        return Response(output_download(job_for_user(request.user, job_id), output_id))


class TrainingWorkspaceDownloadEndpoint(APIView):
    def get(self, request, job_id, area):
        from django.http import FileResponse

        from apps.training.services.downloads import workspace_download

        stream, filename, content_type = workspace_download(
            job_for_user(request.user, job_id),
            area=area,
            path=request.query_params.get("path"),
            revision=request.query_params.get("revision"),
        )
        response = FileResponse(stream, as_attachment=True, filename=filename, content_type=content_type)
        response["Cache-Control"] = "private, no-store"
        return response


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
        return Response(TrainingBuildSerializer(build).data, status=response_status)


class TrainingJobModelOutputEndpoint(APIView):
    def get(self, request, job_id):
        job = job_for_user(request.user, job_id)
        return Response(get_model_output_summary(job))

    def patch(self, request, job_id):
        job = job_for_user(request.user, job_id)
        data = {
            "output_revision": request.data.get("output_revision"),
            "source_code_file": request.FILES.get("source_code_file"),
            "reference_data_file": request.FILES.get("reference_data_file"),
            "remove_assets": request.data.get("remove_assets"),
        }
        if "build_requirements_text" in request.data:
            data["build_requirements_text"] = request.data["build_requirements_text"]
        summary = mutate_training_output(job=job, user=request.user, data=data)
        return Response(summary, status=status.HTTP_200_OK)


class TrainingJobReferencePreviewEndpoint(APIView):
    def get(self, request, job_id):
        job = job_for_user(request.user, job_id)
        return Response(get_job_reference_preview(job))


class TrainingJobOutputsEndpoint(APIView):
    def delete(self, request, job_id):
        job = request_output_purge(job_for_user(request.user, job_id))
        return Response(TrainingJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class TrainingUsageEndpoint(APIView):
    def get(self, request):
        from apps.training.services.quota import usage

        try:
            return Response(usage(request.user))
        except DatabaseError as exc:
            raise ServiceUnavailable("Training quota is temporarily unavailable.") from exc


class TrainingRuntimeCapabilitiesEndpoint(APIView):
    def get(self, request):
        if not settings.TRAINING_ENABLED:
            return Response(
                {
                    "enabled": False,
                    "backend": settings.TRAINING_BACKEND,
                    "cpu_profiles": [],
                    "runtime_options_seconds": [],
                    "accelerators": [],
                }
            )
        accelerators = [{"type": "none", "counts": [0]}]
        local_gpu = None
        local_resources = None
        cpu_profiles = [
            {"id": name, "vcpu": cpu, "memory_mb": memory}
            for name, (cpu, memory) in zip(("small", "medium", "large"), CPU_PROFILES, strict=True)
        ]
        if settings.TRAINING_BACKEND == "docker":
            from apps.training.services.local_resources import capacity, public_capacity

            snapshot = capacity(force=request.query_params.get("refresh") == "1")
            local_resources = public_capacity(snapshot)
            cpu_profiles = snapshot["cpu_profiles"]
            from apps.training.services.local_gpu import inventory

            local_gpu = (
                inventory(force=request.query_params.get("refresh") == "1")
                if settings.TRAINING_GPU_ENABLED and 1 in settings.TRAINING_GPU_COUNTS
                else {"status": "disabled", "reason": "gpu_disabled", "devices": []}
            )
        if settings.TRAINING_GPU_ENABLED and 1 in settings.TRAINING_GPU_COUNTS:
            if settings.TRAINING_BACKEND == "argo":
                accelerators.extend({"type": "gpu", "model": model, "counts": [1]} for model in GPU_MODELS)
            elif local_gpu and local_gpu["status"] == "available":
                accelerators.extend(
                    {"type": "gpu", "model": "", "device_id": device["id"], "counts": [1]}
                    for device in local_gpu["devices"]
                )
        return Response(
            {
                "enabled": bool(cpu_profiles),
                "runtime_options_seconds": runtime_options(),
                "dispatch_timeout_seconds": settings.EXECUTION_DISPATCH_TIMEOUT_SECONDS,
                "backend": settings.TRAINING_BACKEND,
                "cpu_profiles": cpu_profiles,
                "accelerators": accelerators,
                **({"local_gpu": local_gpu} if local_gpu is not None else {}),
                **({"local_resources": local_resources} if local_resources is not None else {}),
            }
        )
