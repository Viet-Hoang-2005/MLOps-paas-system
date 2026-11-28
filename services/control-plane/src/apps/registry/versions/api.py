from rest_framework import generics, status
from rest_framework.response import Response

from apps.catalog.projects.selectors import project_for_user
from apps.registry.models import ModelVersion
from apps.registry.versions.deletion import request_model_version_deletion
from apps.registry.versions.selectors import version_for_user
from apps.registry.versions.serializers import ModelVersionSerializer


class ProjectVersionListEndpoint(generics.ListAPIView):
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

    def destroy(self, request, *args, **kwargs):
        version = version_for_user(request.user, kwargs["version_id"])
        request_model_version_deletion(version)
        return Response({"id": version.public_id, "deletion_requested": True}, status=status.HTTP_202_ACCEPTED)
