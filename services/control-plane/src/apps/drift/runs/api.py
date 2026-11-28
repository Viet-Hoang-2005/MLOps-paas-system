from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.drift.monitors.deletion import delete_drift_run
from apps.drift.runs.lifecycle import request_run
from apps.drift.runs.logs import drift_run_logs
from apps.drift.runs.reports import get_drift_report_data, report_uri_for_run
from apps.drift.runs.serializers import DriftRunSerializer
from apps.drift.selectors import monitor_for_user, run_for_user
from common.api.exceptions import Conflict
from infrastructure.storage import S3Storage
from infrastructure.telemetry.runtime_logs import runtime_log_page


class DriftRunEndpoint(APIView):
    def post(self, request, monitor_id):
        monitor = monitor_for_user(request.user, monitor_id)
        run = request_run(monitor, request.headers.get("Idempotency-Key"))
        return Response(DriftRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class DriftRunLogsEndpoint(APIView):
    def get(self, request, run_id):
        run = run_for_user(request.user, run_id)
        page = runtime_log_page(request, run, "drift", drift_run_logs)
        return Response(
            {
                "run_id": str(run.public_id),
                **page,
                "status": run.status,
                "error_message": run.error_message,
            }
        )


class DriftRunReportURLEndpoint(APIView):
    def get(self, request, run_id):
        run = run_for_user(request.user, run_id)
        if run.status != "completed":
            raise Conflict("The drift report is not available until the run has completed.")
        report_uri = report_uri_for_run(run, "report_html_uri")
        if not report_uri:
            raise Conflict("The completed drift run does not have an HTML report.")
        return Response({"url": S3Storage().presigned_get(report_uri, 900, public=True)})


class DriftRunReportDataEndpoint(APIView):
    def get(self, request, run_id):
        run = run_for_user(request.user, run_id)
        if run.status != "completed":
            raise Conflict("The drift report is not available until the run has completed.")
        return Response(get_drift_report_data(run))


class DriftRunDetailEndpoint(APIView):
    def delete(self, request, run_id):
        run = run_for_user(request.user, run_id)
        delete_drift_run(run)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DriftRunCancelEndpoint(APIView):
    def post(self, request, run_id):
        from apps.drift.runs.lifecycle import request_cancel

        run = run_for_user(request.user, run_id)
        run = request_cancel(run)
        return Response(DriftRunSerializer(run).data, status=status.HTTP_200_OK)
