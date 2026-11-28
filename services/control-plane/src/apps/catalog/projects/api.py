from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.catalog.preview.serializers import (
    ProjectCreateSerializer,
)
from apps.catalog.preview.storage import create_project_preview
from apps.catalog.projects.deletion import request_project_deletion
from apps.catalog.projects.metadata import save_project_metadata
from apps.catalog.projects.selectors import project_for_user
from apps.catalog.projects.serializers import ModelProjectSerializer, ProjectMetadataWriteSerializer
from apps.deployment.builds.serializers import BuildSerializer
from apps.deployment.builds.submission import request_preview_build


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
        from apps.notifications.events import notify_project_created

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
        from apps.notifications.events import notify_project_metadata_updated

        notify_project_metadata_updated(project)
        return Response(ModelProjectSerializer(project).data)

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        project = request_project_deletion(project)
        from apps.notifications.events import notify_project_deleted

        notify_project_deleted(project)
        return Response(ModelProjectSerializer(project).data, status=status.HTTP_202_ACCEPTED)


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
