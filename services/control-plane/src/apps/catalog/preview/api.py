import uuid

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import PreviewAsset
from apps.catalog.preview.serializers import (
    ModelPreviewSerializer,
    NewProjectUploadUrlsRequestSerializer,
    PreviewWriteSerializer,
    ProjectPreviewUploadUrlsRequestSerializer,
)
from apps.catalog.preview.storage import generate_preview_upload_urls, save_preview
from apps.catalog.projects.selectors import project_for_user
from common.api.downloads import scoped_download_response
from common.api.exceptions import Conflict
from infrastructure.storage.paths import preview_committed_prefix


class ProjectPreviewEndpoint(APIView):
    def get(self, request, project_id):
        return Response(ModelPreviewSerializer(project_for_user(request.user, project_id).preview).data)

    def patch(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = PreviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preview = save_preview(project=project, data=serializer.validated_data)
        from apps.notifications.events import notify_project_preview_updated

        notify_project_preview_updated(project)
        return Response(ModelPreviewSerializer(preview).data)


class ProjectPreviewReferenceDownloadEndpoint(APIView):
    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        asset = get_object_or_404(PreviewAsset, preview__project=project, kind="reference_data")
        return scoped_download_response(
            asset.s3_uri,
            prefix=preview_committed_prefix(project.owner.tenant_id, project.public_id),
            filename=asset.name,
        )


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


class PreviewAttributesEndpoint(APIView):
    def get(self, request, project_id):
        from apps.catalog.running.snapshots import preview_attributes

        return Response(preview_attributes(project_for_user(request.user, project_id)))
