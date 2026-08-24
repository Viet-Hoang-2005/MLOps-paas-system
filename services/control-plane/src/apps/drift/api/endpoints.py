from common.api.exceptions import Conflict
from django.conf import settings
from infrastructure.storage import S3Storage
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.drift.selectors import monitor_for_user, monitors_for_user, run_for_user
from apps.drift.services.logs import drift_run_logs
from apps.drift.services.runs import request_run

from .serializers import DriftMonitorSerializer, DriftRunSerializer


class DriftMonitorListCreateEndpoint(generics.ListCreateAPIView):
    serializer_class = DriftMonitorSerializer

    def get_queryset(self):
        return monitors_for_user(self.request.user).prefetch_related("runs")

    def perform_create(self, serializer):
        serializer.save(backend=settings.DRIFT_BACKEND)


class DriftMonitorDetailEndpoint(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DriftMonitorSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "monitor_id"

    def get_queryset(self):
        return monitors_for_user(self.request.user).prefetch_related("runs")


class DriftRunEndpoint(APIView):
    def post(self, request, monitor_id):
        monitor = monitor_for_user(request.user, monitor_id)
        run = request_run(monitor, request.headers.get("Idempotency-Key"))
        return Response(DriftRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class DriftRunLogsEndpoint(APIView):
    def get(self, request, run_id):
        try:
            offset = int(request.query_params.get("offset", "0"))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"offset": "Must be a non-negative integer."}) from exc
        if offset < 0:
            raise ValidationError({"offset": "Must be a non-negative integer."})

        run = run_for_user(request.user, run_id)
        logs, next_offset = drift_run_logs(run, offset)
        return Response(
            {
                "run_id": str(run.public_id),
                "logs": logs,
                "next_offset": next_offset,
                "status": run.status,
                "error_message": run.error_message,
            }
        )


class DriftRunReportURLEndpoint(APIView):
    def get(self, request, run_id):
        run = run_for_user(request.user, run_id)
        if run.status != "completed":
            raise Conflict("The drift report is not available until the run has completed.")
        if not run.report_html_uri:
            raise Conflict("The completed drift run does not have an HTML report.")
        return Response({"url": S3Storage().presigned_get(run.report_html_uri, 900)})
