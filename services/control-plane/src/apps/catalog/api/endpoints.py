from django.conf import settings
from infrastructure.storage import S3Storage
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.catalog.selectors import project_for_user
from apps.catalog.services.deletion import request_project_deletion
from apps.catalog.services.project_metadata import save_project_metadata
from apps.catalog.services.workspace import save_workspace_file
from apps.deployment.api.serializers import (
    BuildSerializer,
    ManualBuildCreateSerializer,
    PresignedUploadUrlSerializer,
)
from apps.deployment.services.builds import create_build_presigned_url, request_manual_build

from .serializers import (
    ModelProjectSerializer,
    ProjectMetadataWriteSerializer,
    WorkspaceAssetSerializer,
    WorkspaceUploadSerializer,
)


class ModelProjectListCreateEndpoint(generics.ListCreateAPIView):
    serializer_class = ModelProjectSerializer

    def get_queryset(self):
        return (
            ModelProject.objects.filter(owner=self.request.user, is_active=True)
            .prefetch_related("workspace_assets", "versions__deployments__endpoint", "builds")
        )

    def create(self, request, *args, **kwargs):
        serializer = ProjectMetadataWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = save_project_metadata(actor=request.user, validated_data=serializer.validated_data)
        return Response(ModelProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class ModelProjectDetailEndpoint(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ModelProjectSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "project_id"

    def get_queryset(self):
        return (
            ModelProject.objects.filter(owner=self.request.user, is_active=True)
            .prefetch_related("workspace_assets", "versions__deployments__endpoint", "builds")
        )

    def update(self, request, *args, **kwargs):
        project = self.get_object()
        serializer = ProjectMetadataWriteSerializer(data=request.data)
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
        relative_path = str(request.data.get("relative_path", ""))
        asset = project.workspace_assets.filter(kind=kind, relative_path=relative_path).first()
        if not asset:
            return Response(status=status.HTTP_204_NO_CONTENT)
        S3Storage().delete(asset.s3_uri)
        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectBuildEndpoint(APIView):
    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        return Response(BuildSerializer(project.builds.all(), many=True).data)

    def post(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = ManualBuildCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        build = request_manual_build(
            project=project,
            validated_data=serializer.validated_data,
            backend=settings.BUILD_BACKEND,
        )
        return Response(BuildSerializer(build).data, status=status.HTTP_201_CREATED)


class ProjectBuildUploadUrlEndpoint(APIView):
    def post(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = PresignedUploadUrlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_build_presigned_url(
            project=project,
            validated_data=serializer.validated_data,
        )
        return Response(result, status=status.HTTP_200_OK)
