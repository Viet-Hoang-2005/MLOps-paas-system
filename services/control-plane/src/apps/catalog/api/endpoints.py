from django.conf import settings
from django.db import transaction
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.catalog.selectors import project_for_user
from apps.catalog.services.deletion import request_project_deletion
from apps.catalog.services.draft import (
    complete_draft_asset_upload,
    create_draft_asset_upload_url,
    delete_draft_asset,
    dispatch_draft_build,
    discard_draft,
    get_project_overview,
    load_version_into_draft,
    save_draft,
)
from apps.catalog.services.project_metadata import save_project_metadata
from apps.deployment.api.serializers import BuildSerializer
from common.api.exceptions import Conflict

from .serializers import (
    DraftAssetCompleteSerializer,
    DraftAssetSerializer,
    DraftAssetUploadUrlSerializer,
    DraftBuildSerializer,
    DraftLoadVersionSerializer,
    DraftSaveSerializer,
    ModelDraftSerializer,
    ModelDraftUpdateSerializer,
    ModelProjectSerializer,
    ProjectMetadataWriteSerializer,
)


class ModelProjectListCreateEndpoint(generics.ListCreateAPIView):
    serializer_class = ModelProjectSerializer

    def get_queryset(self):
        return ModelProject.objects.filter(owner=self.request.user, is_active=True).prefetch_related(
            "versions__deployments__endpoint", "builds"
        )

    def create(self, request, *args, **kwargs):
        serializer = ProjectMetadataWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data.get("name"):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"name": "This field is required."})
        project = save_project_metadata(actor=request.user, validated_data=serializer.validated_data)
        return Response(ModelProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class ModelProjectDetailEndpoint(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ModelProjectSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "project_id"

    def get_queryset(self):
        return ModelProject.objects.filter(owner=self.request.user, is_active=True).prefetch_related(
            "versions__deployments__endpoint", "builds"
        )

    def update(self, request, *args, partial=False, **kwargs):
        project = self.get_object()
        serializer = ProjectMetadataWriteSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("At least one project metadata field is required.")
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


class ProjectBuildEndpoint(APIView):
    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        return Response(BuildSerializer(project.builds.all(), many=True).data)

class ModelProjectOverviewEndpoint(APIView):
    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        overview_data = get_project_overview(project=project)
        return Response(overview_data, status=status.HTTP_200_OK)


class ModelDraftDetailEndpoint(APIView):
    def get(self, request, project_id):
        project = project_for_user(request.user, project_id)
        return Response(ModelDraftSerializer(project.current_draft).data, status=status.HTTP_200_OK)

    def put(self, request, project_id):
        return self._update(request, project_id)

    def patch(self, request, project_id):
        return self._update(request, project_id)

    def _update(self, request, project_id):
        serializer = ModelDraftUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        project = project_for_user(request.user, project_id)
        with transaction.atomic():
            draft = type(project.current_draft).objects.select_for_update().get(pk=project.current_draft.pk)
            if draft.status in {"locked", "saving"}:
                raise Conflict("Cannot update Draft while it is locked or saving.")
            if data.pop("expected_revision") != draft.revision:
                raise Conflict("Draft revision changed. Reload before editing.")
            for field in ("flavor", "artifact_format", "requirements_snapshot"):
                if field in data:
                    setattr(draft, field, data[field])
            draft.revision += 1
            draft.status = "editing"
            draft.save()
        return Response(ModelDraftSerializer(draft).data, status=status.HTTP_200_OK)


class ModelDraftSaveEndpoint(APIView):
    def post(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = DraftSaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = save_draft(
            draft=project.current_draft,
            expected_revision=serializer.validated_data["expected_revision"],
        )
        return Response(ModelDraftSerializer(draft).data, status=status.HTTP_200_OK)

class ModelDraftDiscardEndpoint(APIView):
    def post(self, request, project_id):
        project = project_for_user(request.user, project_id)
        return Response(ModelDraftSerializer(discard_draft(draft=project.current_draft)).data)


class ModelDraftAssetUploadUrlEndpoint(APIView):
    def post(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = DraftAssetUploadUrlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_draft_asset_upload_url(
            draft=project.current_draft,
            user=request.user,
            kind=serializer.validated_data["kind"],
            filename=serializer.validated_data["filename"],
            content_type=serializer.validated_data.get("content_type", "application/octet-stream"),
            size_bytes=serializer.validated_data.get("size_bytes", 0),
            checksum=serializer.validated_data.get("checksum", ""),
        )
        return Response(result, status=status.HTTP_200_OK)


class ModelDraftAssetCompleteEndpoint(APIView):
    def post(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = DraftAssetCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = complete_draft_asset_upload(
            draft=project.current_draft,
            user=request.user,
            upload_id=serializer.validated_data["upload_id"],
        )
        return Response(DraftAssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class ModelDraftAssetDeleteEndpoint(APIView):
    def delete(self, request, project_id, kind):
        project = project_for_user(request.user, project_id)
        delete_draft_asset(draft=project.current_draft, kind=kind)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ModelDraftBuildEndpoint(APIView):
    def post(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = DraftBuildSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        backend = serializer.validated_data.get("backend") or getattr(settings, "BUILD_BACKEND", "docker")
        build = dispatch_draft_build(
            draft=project.current_draft,
            actor=request.user,
            backend=backend,
        )
        return Response(BuildSerializer(build).data, status=status.HTTP_201_CREATED)


class ModelDraftLoadVersionEndpoint(APIView):
    def post(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = DraftLoadVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = load_version_into_draft(
            draft=project.current_draft,
            version_id=serializer.validated_data["version_id"],
            confirm=serializer.validated_data.get("confirm", False),
        )
        return Response(ModelDraftSerializer(draft).data, status=status.HTTP_200_OK)
