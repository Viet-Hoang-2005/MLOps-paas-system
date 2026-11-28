from django.conf import settings
from django.db import transaction
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import ModelProject
from apps.drift.monitors.deletion import request_drift_monitor_deletion
from apps.drift.monitors.reference import get_monitor_reference_preview, reference_download_url
from apps.drift.monitors.serializers import DriftMonitorSerializer
from apps.drift.runs.serializers import DriftRunSerializer
from apps.drift.selectors import monitor_for_user, monitors_for_user
from common.api.downloads import scoped_download_response
from common.api.exceptions import Conflict
from infrastructure.storage.paths import project_prefix, version_prefix


class DriftMonitorListCreateEndpoint(generics.ListCreateAPIView):
    serializer_class = DriftMonitorSerializer

    def get_queryset(self):
        from django.db.models import Prefetch

        from apps.drift.models import DriftRun

        return (
            monitors_for_user(self.request.user)
            .select_related("version", "version__project")
            .prefetch_related(
                Prefetch("runs", queryset=DriftRun.objects.select_related("monitor__version__project"))
            )
        )

    def perform_create(self, serializer):
        from apps.drift.monitors.reference import create_monitor

        serializer.instance = create_monitor(
            data=serializer.validated_data,
            backend=settings.DRIFT_BACKEND,
        )


class DriftMonitorDetailEndpoint(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DriftMonitorSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "monitor_id"

    def get_queryset(self):
        from django.db.models import Prefetch

        from apps.drift.models import DriftRun

        return (
            monitors_for_user(self.request.user)
            .select_related("version", "version__project")
            .prefetch_related(
                Prefetch("runs", queryset=DriftRun.objects.select_related("monitor__version__project"))
            )
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        monitor = monitor_for_user(request.user, kwargs["monitor_id"])
        project = ModelProject.objects.select_for_update().filter(pk=monitor.version.project_id).first()
        if not project or project.deletion_state != "active":
            raise Conflict("This project is being deleted.")
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        if serializer.instance.deletion_requested or serializer.instance.version.deletion_requested:
            raise Conflict("This drift monitor or model version is being deleted.")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        monitor = monitor_for_user(request.user, kwargs["monitor_id"])
        request_drift_monitor_deletion(monitor)
        return Response({"id": monitor.public_id, "deletion_requested": True}, status=status.HTTP_202_ACCEPTED)


class DriftMonitorReferenceURLEndpoint(APIView):
    def get(self, request, monitor_id):
        monitor = monitor_for_user(request.user, monitor_id)
        if request.query_params.get("download") == "1":
            version = monitor.version
            project = version.project
            if monitor.deletion_requested or version.deletion_requested or project.deletion_state != "active" or not project.is_active:
                raise Conflict("This drift reference is unavailable.")
            tenant = project.owner.tenant_id
            return scoped_download_response(
                monitor.reference_uri,
                prefix=(
                    version_prefix(tenant, project.public_id, version.public_id) + "/",
                    f"{project_prefix(tenant, project.public_id)}/drift/{monitor.public_id}/",
                ),
                filename=monitor.reference_name or "reference.csv",
            )
        return Response({"url": reference_download_url(monitor)})


class DriftMonitorReferencePreviewEndpoint(APIView):
    def get(self, request, monitor_id):
        monitor = monitor_for_user(request.user, monitor_id)
        return Response(get_monitor_reference_preview(monitor))


class DriftMonitorCancelEndpoint(APIView):
    def post(self, request, monitor_id):
        from apps.drift.runs.lifecycle import request_cancel

        monitor = monitor_for_user(request.user, monitor_id)
        active_run = monitor.runs.filter(status__in=["pending", "queued", "running"]).order_by("-created_at").first()
        if not active_run:
            raise Conflict("No active run found for this monitor.")
        active_run = request_cancel(active_run)
        return Response(DriftRunSerializer(active_run).data, status=status.HTTP_200_OK)
