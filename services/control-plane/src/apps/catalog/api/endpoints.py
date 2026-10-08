import uuid

from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.catalog.selectors import project_for_user
from apps.catalog.services.deletion import request_project_deletion
from apps.catalog.services.preview import (
    create_project_preview,
    generate_preview_upload_urls,
    save_preview,
)
from apps.catalog.services.project_metadata import save_project_metadata
from apps.catalog.services.workspace import delete_workspace_file, save_workspace_file
from apps.deployment.api.serializers import (
    BuildSerializer,
)
from apps.deployment.services.builds import request_preview_build
from common.api.exceptions import Conflict

from .serializers import (
    ModelPreviewSerializer,
    ModelProjectSerializer,
    NewProjectUploadUrlsRequestSerializer,
    PreviewWriteSerializer,
    ProjectCreateSerializer,
    ProjectMetadataWriteSerializer,
    ProjectPreviewUploadUrlsRequestSerializer,
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
        serializer = ProjectCreateSerializer(data=request.data, context={"request": request})
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


class ProjectPreviewUploadUrlsEndpoint(APIView):
    def post(self, request, project_id):
        project = project_for_user(request.user, project_id)
        if not project.is_active or project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        serializer = ProjectPreviewUploadUrlsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        flavor = serializer.validated_data.get("flavor") or project.preview.flavor
        artifact_format = serializer.validated_data.get("artifact_format") or project.preview.artifact_format
        files = generate_preview_upload_urls(
            tenant_id=project.owner.tenant_id,
            project_id=str(project.public_id),
            files_data=serializer.validated_data["files"],
            flavor=flavor,
            artifact_format=artifact_format,
        )
        return Response({"project_id": str(project.public_id), "files": files})


class ProjectCreateUploadUrlsEndpoint(APIView):
    def post(self, request):
        serializer = NewProjectUploadUrlsRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        project_id = uuid.uuid4()
        tenant_id = request.user.tenant_id
        files = generate_preview_upload_urls(
            tenant_id=tenant_id,
            project_id=str(project_id),
            files_data=serializer.validated_data["files"],
            flavor=serializer.validated_data.get("flavor"),
            artifact_format=serializer.validated_data.get("artifact_format", "raw"),
        )
        return Response({"project_id": str(project_id), "files": files})


class ProjectPreviewReferencePreviewEndpoint(APIView):
    def get(self, request, project_id):
        from apps.catalog.services.preview import get_preview_reference_preview

        project = project_for_user(request.user, project_id)
        return Response(get_preview_reference_preview(project))


class RunningSourceEndpoint(APIView):
    def get(self, request, project_id):
        from apps.catalog.services.snapshots import running_source

        project = project_for_user(request.user, project_id)
        version_id = request.query_params.get("version_id")
        return Response({"content": running_source(project, version_id=version_id)})


class RunningAttributesEndpoint(APIView):
    def get(self, request, project_id):
        from apps.catalog.services.snapshots import running_attributes

        project = project_for_user(request.user, project_id)
        version_id = request.query_params.get("version_id")
        return Response(running_attributes(project, version_id=version_id))


class PreviewAttributesEndpoint(APIView):
    def get(self, request, project_id):
        from apps.catalog.services.snapshots import preview_attributes

        return Response(preview_attributes(project_for_user(request.user, project_id)))


class RunningLabelMappingEndpoint(APIView):
    def get(self, request, project_id):
        from apps.catalog.services.snapshots import running_label_mapping

        project = project_for_user(request.user, project_id)
        version_id = request.query_params.get("version_id")
        result = running_label_mapping(project, version_id=version_id)
        if result is None:
            return Response({"filename": "", "mapping": {}}, status=status.HTTP_200_OK)
        return Response(result)


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
