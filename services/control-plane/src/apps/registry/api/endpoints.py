from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.selectors import project_for_user
from apps.deployment.api.serializers import BuildSerializer
from apps.registry.models import ModelVersion, RegistryAlias
from apps.registry.selectors import version_for_user
from apps.registry.services.routing import predict_alias, predict_version
from apps.registry.services.versions import request_version_rebuild

from .serializers import ModelVersionSerializer, RegistryAliasSerializer


class ProjectVersionListCreateEndpoint(generics.ListAPIView):
    serializer_class = ModelVersionSerializer

    def project(self):
        if not hasattr(self, "_project"):
            self._project = project_for_user(self.request.user, self.kwargs["project_id"])
        return self._project

    def get_queryset(self):
        return (
            ModelVersion.objects.filter(project=self.project())
            .select_related("source_job")
            .prefetch_related("artifacts")
        )

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "project": self.project()}


class ModelVersionDetailEndpoint(generics.RetrieveAPIView):
    serializer_class = ModelVersionSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "version_id"

    def get_queryset(self):
        return (
            ModelVersion.objects.filter(project__owner=self.request.user)
            .select_related("project", "source_job")
            .prefetch_related("artifacts", "metrics")
        )


class ProjectAliasListCreateEndpoint(generics.ListAPIView):
    serializer_class = RegistryAliasSerializer

    def project(self):
        if not hasattr(self, "_project"):
            self._project = project_for_user(self.request.user, self.kwargs["project_id"])
        return self._project

    def get_queryset(self):
        return RegistryAlias.objects.filter(project=self.project()).select_related("version")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "project": self.project()}

class AliasPredictionEndpoint(APIView):
    def post(self, request, project_id, alias_name):
        project = project_for_user(request.user, project_id)
        return Response(
            predict_alias(
                project=project,
                alias_name=alias_name,
                payload=request.data,
            )
        )


class VersionSmokeTestEndpoint(APIView):
    def post(self, request, version_id):
        version = version_for_user(request.user, version_id)
        return Response(predict_version(version=version, payload=request.data))


class ModelVersionRebuildEndpoint(APIView):
    def post(self, request, version_id):
        version = version_for_user(request.user, version_id)
        backend = request.data.get("backend") or getattr(settings, "BUILD_BACKEND", "docker")
        build = request_version_rebuild(
            version=version,
            actor=request.user,
            backend=backend,
        )
        return Response(BuildSerializer(build).data, status=status.HTTP_201_CREATED)
