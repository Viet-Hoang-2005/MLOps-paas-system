from django.db.models import Count, Max, Prefetch, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.training.models import TrainingJob, TrainingWorkspace
from apps.training.services import drafts, workspaces
from apps.training.services.downloads import workspace_download
from apps.training.services.workspace_lifecycle import request_workspace_deletion

from .serializers import TrainingDraftSettingsSerializer, TrainingJobSerializer, TrainingSubmissionSerializer
from .workspaces import _workspace


class WorkspaceSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status = serializers.CharField(read_only=True)
    entries = serializers.SerializerMethodField()
    secrets = serializers.SerializerMethodField()
    secrets_available = serializers.SerializerMethodField()
    job_count = serializers.SerializerMethodField()
    active_job_id = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()

    class Meta:
        model = TrainingWorkspace
        fields = (
            "id",
            "revision",
            "status",
            "entry_point",
            "environment",
            "model_flavor",
            "vcpu",
            "memory_mb",
            "max_runtime_seconds",
            "accelerator_type",
            "accelerator_count",
            "accelerator_model",
            "local_gpu_id",
            "entries",
            "secrets",
            "secrets_available",
            "job_count",
            "active_job_id",
            "deletion_requested_at",
            "deletion_error",
            "created_at",
            "updated_at",
        )

    def get_entries(self, obj):
        return workspaces.serialize_entries(obj.entries.order_by("relative_path")) if self.context.get("detail") else []

    def get_secrets(self, obj):
        return list(obj.secrets.values("name", "updated_at")) if self.context.get("detail") else []

    def get_secrets_available(self, obj):
        try:
            workspaces.cipher()
            return True
        except workspaces.ServiceUnavailable:
            return False

    def get_job_count(self, obj):
        return obj.total_jobs if hasattr(obj, "total_jobs") else obj.jobs.count()

    def get_active_job_id(self, obj):
        prefetched = getattr(obj, "_display_active_jobs", None)
        job = (prefetched[0] if prefetched else None) if prefetched is not None else obj.active_jobs().first()
        return str(job.public_id) if job else None

    def get_updated_at(self, obj):
        latest = getattr(obj, "latest_job_update", None)
        return max(obj.updated_at, latest).isoformat() if latest else obj.updated_at.isoformat()


class WorkspaceList(APIView):
    def get(self, request):
        rows = (
            TrainingWorkspace.objects.filter(owner=request.user)
            .annotate(total_jobs=Count("jobs", distinct=True), latest_job_update=Max("jobs__updated_at"))
            .prefetch_related(
                Prefetch(
                    "jobs",
                    queryset=TrainingJob.objects.filter(TrainingWorkspace.active_filter()),
                    to_attr="_display_active_jobs",
                )
            )
        )
        project = request.query_params.get("project")
        if project == "unassigned":
            rows = rows.filter(Q(jobs__project__isnull=True))
        elif project:
            project = serializers.UUIDField().run_validation(project)
            rows = rows.filter(jobs__project__public_id=project)
        return Response({"workspaces": WorkspaceSerializer(rows.distinct(), many=True).data})

    def post(self, request):
        data = TrainingDraftSettingsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = drafts.create_workspace(owner=request.user, values=data.validated_data)
        return Response(WorkspaceSerializer(row, context={"detail": True}).data, status=201)


class WorkspaceDetail(APIView):
    def get(self, request, workspace_id):
        return Response(WorkspaceSerializer(_workspace(request.user, workspace_id), context={"detail": True}).data)

    def patch(self, request, workspace_id):
        data = TrainingDraftSettingsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        row = workspaces.update_workspace(
            _workspace(request.user, workspace_id), revision=values.pop("revision", None), changes=values
        )
        return Response(WorkspaceSerializer(row, context={"detail": True}).data)

    def delete(self, request, workspace_id):
        request_workspace_deletion(_workspace(request.user, workspace_id))
        return Response({"deletion_pending": True}, status=202)


class WorkspaceRuns(APIView):
    def post(self, request, workspace_id):
        from .endpoints import require_training_enabled

        require_training_enabled()
        data = TrainingSubmissionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        job = drafts.run_workspace(_workspace(request.user, workspace_id), **data.validated_data)
        return Response(TrainingJobSerializer(job).data, status=201)


class WorkspaceJobs(APIView):
    def get(self, request, workspace_id):
        workspace = _workspace(request.user, workspace_id)
        page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("page", 1))
        rows = workspace.jobs.filter(owner=request.user).select_related("workspace", "project").order_by("-created_at")
        return Response(
            {
                "training_jobs": TrainingJobSerializer(rows[(page - 1) * 20 : page * 20], many=True).data,
                "count": rows.count(),
                "page": page,
                "page_size": 20,
            }
        )


class WorkspaceJob(APIView):
    def get(self, request, workspace_id, job_id):
        workspace = _workspace(request.user, workspace_id)
        job = get_object_or_404(workspace.jobs.filter(owner=request.user), public_id=job_id)
        return Response(TrainingJobSerializer(job).data)


class WorkspaceDownload(APIView):
    def get(self, request, workspace_id):
        stream, filename, content_type = workspace_download(
            _workspace(request.user, workspace_id),
            area="input",
            path=request.query_params.get("path"),
            revision=request.query_params.get("revision"),
        )
        return FileResponse(stream, as_attachment=True, filename=filename, content_type=content_type)
