from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.selectors import project_for_user
from apps.registry.models import ModelVersion, RegistryAlias
from apps.registry.selectors import version_for_user
from apps.registry.services.deletion import delete_model_version
from apps.registry.services.routing import predict_alias, predict_version
from apps.registry.services.versions import (
    add_supplemental_artifacts,
    get_version_reference_preview,
    set_alias,
)

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
            .prefetch_related("artifacts", "metrics")
        )

    def list(self, request, *args, **kwargs):
        from collections import defaultdict
        from apps.observability.models import LifecycleEvent

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        items = list(page if page is not None else queryset)
        events_by_version_id = defaultdict(list)
        if items:
            version_ids = [item.public_id for item in items]
            for ev in LifecycleEvent.objects.filter(
                aggregate_type="model_version", aggregate_id__in=version_ids
            ).order_by("-created_at"):
                events_by_version_id[ev.aggregate_id].append(ev)
        context = {**self.get_serializer_context(), "events_by_version_id": events_by_version_id}
        serializer = self.get_serializer(items, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "project": self.project()}


class ModelVersionDetailEndpoint(generics.RetrieveDestroyAPIView):
    serializer_class = ModelVersionSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "version_id"

    def get_queryset(self):
        return (
            ModelVersion.objects.filter(project__owner=self.request.user)
            .select_related("project", "source_job")
            .prefetch_related("artifacts", "metrics")
        )

    def perform_destroy(self, instance):
        delete_model_version(instance)


class ModelVersionSupplementalArtifactsEndpoint(APIView):
    def post(self, request, version_id):
        version = version_for_user(request.user, version_id)
        updated = add_supplemental_artifacts(
            version=version,
            actor=request.user,
            source_code_file=request.FILES.get("source_code_file"),
            reference_data_file=request.FILES.get("reference_data_file"),
            label_mapping_file=request.FILES.get("label_mapping_file"),
            input_schema_file=request.FILES.get("input_schema_file"),
            metrics_file=request.FILES.get("metrics_file"),
            params_file=request.FILES.get("params_file"),
            model_insights_file=request.FILES.get("model_insights_file"),
            feature_importance_file=request.FILES.get("feature_importance_file"),
        )
        return Response(ModelVersionSerializer(updated).data)


class ModelVersionReferencePreviewEndpoint(APIView):
    def get(self, request, version_id):
        version = version_for_user(request.user, version_id)
        return Response(get_version_reference_preview(version))
