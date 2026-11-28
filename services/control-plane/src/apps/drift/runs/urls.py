from django.urls import path

from apps.drift.runs.api import (
    DriftRunCancelEndpoint,
    DriftRunDetailEndpoint,
    DriftRunLogsEndpoint,
    DriftRunReportDataEndpoint,
    DriftRunReportURLEndpoint,
)

urlpatterns = [
    path("<uuid:run_id>/", DriftRunDetailEndpoint.as_view(), name="drift-run-detail"),
    path("<uuid:run_id>/cancel/", DriftRunCancelEndpoint.as_view(), name="drift-run-cancel"),
    path("<uuid:run_id>/logs/", DriftRunLogsEndpoint.as_view(), name="drift-run-logs"),
    path("<uuid:run_id>/report-url/", DriftRunReportURLEndpoint.as_view(), name="drift-run-report-url"),
    path("<uuid:run_id>/report-data/", DriftRunReportDataEndpoint.as_view(), name="drift-run-report-data"),
]
