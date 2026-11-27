import uuid

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject, PreviewAsset
from apps.catalog.selectors import project_for_user
from apps.catalog.services.deletion import request_project_deletion
from apps.catalog.services.preview import (
    create_project_preview,
    generate_preview_upload_urls,
    save_preview,
)
from apps.catalog.services.project_metadata import save_project_metadata
from apps.deployment.api.serializers import (
    BuildSerializer,
)
from apps.deployment.services.builds import request_preview_build
from common.api.downloads import scoped_download_response
from common.api.exceptions import Conflict
from infrastructure.storage.paths import preview_committed_prefix

from .serializers import (
    ModelPreviewSerializer,
    ModelProjectSerializer,
    NewProjectUploadUrlsRequestSerializer,
    PreviewWriteSerializer,
    ProjectCreateSerializer,
    ProjectMetadataWriteSerializer,
    ProjectPreviewUploadUrlsRequestSerializer,
)


class ModelProjectListCreateEndpoint(generics.ListCreateAPIView):
    serializer_class = ModelProjectSerializer

    def get_queryset(self):
        from django.db.models import Exists, OuterRef, Subquery
        from apps.registry.models import ModelVersion

        version_qs = ModelVersion.objects.filter(project_id=OuterRef("pk"))
        return (
            ModelProject.objects.filter(owner=self.request.user)
            .exclude(deletion_state="deleted")
            .select_related(
                "preview", "active_deployment__version", "active_deployment__endpoint", "active_deployment__build"
            )
            .prefetch_related("active_deployment__version__artifacts")
            .annotate(
                _has_versions=Exists(version_qs),
                _latest_version_id=Subquery(version_qs.order_by("-registered_at", "-id").values("public_id")[:1]),
                _latest_version_number=Subquery(version_qs.order_by("-registered_at", "-id").values("version")[:1]),
            )
        )

    def create(self, request, *args, **kwargs):
        serializer = ProjectCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        project = create_project_preview(actor=request.user, data=serializer.validated_data)
        from apps.notifications.hooks import notify_project_created

        notify_project_created(project)
        return Response(ModelProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class ModelProjectDetailEndpoint(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ModelProjectSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "project_id"

    def get_queryset(self):
        from django.db.models import Exists, OuterRef, Subquery
        from apps.registry.models import ModelVersion

        version_qs = ModelVersion.objects.filter(project_id=OuterRef("pk"))
        return (
            ModelProject.objects.filter(owner=self.request.user)
            .exclude(deletion_state="deleted")
            .select_related(
                "preview", "active_deployment__version", "active_deployment__endpoint", "active_deployment__build"
            )
            .prefetch_related("active_deployment__version__artifacts")
            .annotate(
                _has_versions=Exists(version_qs),
                _latest_version_id=Subquery(version_qs.order_by("-registered_at", "-id").values("public_id")[:1]),
                _latest_version_number=Subquery(version_qs.order_by("-registered_at", "-id").values("version")[:1]),
            )
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
        from apps.notifications.hooks import notify_project_metadata_updated

        notify_project_metadata_updated(project)
        return Response(ModelProjectSerializer(project).data)

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        project = request_project_deletion(project)
        from apps.notifications.hooks import notify_project_deleted

        notify_project_deleted(project)
        return Response(ModelProjectSerializer(project).data, status=status.HTTP_202_ACCEPTED)


class ProjectPreviewEndpoint(APIView):
    def get(self, request, project_id):
        return Response(ModelPreviewSerializer(project_for_user(request.user, project_id).preview).data)

    def patch(self, request, project_id):
        project = project_for_user(request.user, project_id)
        serializer = PreviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preview = save_preview(project=project, data=serializer.validated_data)
        from apps.notifications.hooks import notify_project_preview_updated

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
