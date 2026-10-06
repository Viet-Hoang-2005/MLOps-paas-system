from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.catalog.selectors import project_for_user
from apps.catalog.services.deletion import request_project_deletion
from apps.catalog.services.preview import create_project_preview, save_preview
from apps.catalog.services.project_metadata import save_project_metadata
from apps.catalog.services.workspace import delete_workspace_file, save_workspace_file
from apps.deployment.api.serializers import (
    BuildSerializer,
)
from apps.deployment.services.builds import request_preview_build

from .serializers import (
    ModelPreviewSerializer,
    ModelProjectSerializer,
    PreviewWriteSerializer,
    ProjectCreateSerializer,
    ProjectMetadataWriteSerializer,
    WorkspaceAssetSerializer,
    WorkspaceUploadSerializer,
)


class ModelProjectListCreateEndpoint(generics.ListCreateAPIView):
    serializer_class = ModelProjectSerializer

    def get_queryset(self):
        return (
            ModelProject.objects.filter(owner=self.request.user)
            .exclude(deletion_state="deleted")
            .select_related("preview", "active_deployment__version", "active_deployment__endpoint", "active_deployment__build")
            .prefetch_related("workspace_assets", "versions__deployments__endpoint", "builds")
        )

    def create(self, request, *args, **kwargs):
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = create_project_preview(actor=request.user, data=serializer.validated_data)
        return Response(ModelProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class ModelProjectDetailEndpoint(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ModelProjectSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "project_id"

    def get_queryset(self):
        return (
            ModelProject.objects.filter(owner=self.request.user)
            .exclude(deletion_state="deleted")
            .select_related("preview", "active_deployment__version", "active_deployment__endpoint", "active_deployment__build")
            .prefetch_related("workspace_assets", "versions__deployments__endpoint", "builds")
        )

    def update(self, request, *args, **kwargs):
        project = self.get_object()
        serializer = ProjectMetadataWriteSerializer(data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        project = save_project_metadata(
            actor=request.user,
            project=project,
            validated_data=serializer.validated_data,
        )
        return Response(ModelProjectSerializer(project).data)

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        project = request_project_deletion(project)
        return Response(ModelProjectSerializer(project).data, status=status.HTTP_202_ACCEPTED)


class TrainingProjectCreateEndpoint(APIView):
    def post(self, request):
        serializer = ProjectMetadataWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = save_project_metadata(actor=request.user, validated_data=serializer.validated_data)
        return Response(ModelProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class WorkspaceFilesEndpoint(APIView):
    def get(self, request, project_id, kind):
        project = project_for_user(request.user, project_id)
        return Response(WorkspaceAssetSerializer(project.workspace_assets.filter(kind=kind), many=True).data)

    def post(self, request, project_id, kind):
        project = project_for_user(request.user, project_id)
        serializer = WorkspaceUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = save_workspace_file(
            project=project,
            kind=kind,
            relative_path=serializer.validated_data["relative_path"],
            uploaded_file=serializer.validated_data["file"],
        )
        return Response(WorkspaceAssetSerializer(asset).data, status=status.HTTP_201_CREATED)

    def delete(self, request, project_id, kind):
        project = project_for_user(request.user, project_id)
        delete_workspace_file(project=project, kind=kind, relative_path=str(request.data.get("relative_path", "")))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectPreviewEndpoint(APIView):
    def get(self, request, project_id):
        return Response(ModelPreviewSerializer(project_for_user(request.user, project_id).preview).data)

    def patch(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = PreviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preview = save_preview(project=project, data=serializer.validated_data)
        return Response(ModelPreviewSerializer(preview).data)


class ProjectPreviewReferencePreviewEndpoint(APIView):
    def get(self, request, project_id):
        from apps.catalog.services.preview import get_preview_reference_preview

        project = project_for_user(request.user, project_id)
        return Response(get_preview_reference_preview(project))


class RunningSourceEndpoint(APIView):
    def get(self, request, project_id):
        from apps.catalog.services.snapshots import running_source

        return Response({"content": running_source(project_for_user(request.user, project_id))})


class ProjectBuildEndpoint(APIView):
    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        return Response(BuildSerializer(project.builds.all(), many=True).data)

    def post(self, request, project_id):
        project = project_for_user(request.user, project_id)
        from rest_framework import serializers

        revision = serializers.IntegerField(min_value=1).run_validation(request.data.get("revision"))
        build = request_preview_build(project=project, revision=revision, backend=settings.BUILD_BACKEND)
        return Response(BuildSerializer(build).data, status=status.HTTP_201_CREATED)

