from django.urls import path

from .endpoints import (
    DriftMonitorCancelEndpoint,
    DriftMonitorDetailEndpoint,
    DriftMonitorListCreateEndpoint,
    DriftMonitorReferencePreviewEndpoint,
    DriftMonitorReferenceURLEndpoint,
    DriftRunCancelEndpoint,
    DriftRunDetailEndpoint,
    DriftRunEndpoint,
    DriftRunLogsEndpoint,
    DriftRunReportDataEndpoint,
    DriftRunReportURLEndpoint,
)

urlpatterns = [
    path("", DriftMonitorListCreateEndpoint.as_view(), name="drift-monitor-list"),
    path("runs/<uuid:run_id>/", DriftRunDetailEndpoint.as_view(), name="drift-run-detail"),
    path("runs/<uuid:run_id>/cancel/", DriftRunCancelEndpoint.as_view(), name="drift-run-cancel"),
    path("runs/<uuid:run_id>/logs/", DriftRunLogsEndpoint.as_view(), name="drift-run-logs"),
    path("runs/<uuid:run_id>/report-url/", DriftRunReportURLEndpoint.as_view(), name="drift-run-report-url"),
    path("runs/<uuid:run_id>/report-data/", DriftRunReportDataEndpoint.as_view(), name="drift-run-report-data"),
    path("<uuid:monitor_id>/", DriftMonitorDetailEndpoint.as_view(), name="drift-monitor-detail"),
    path("<uuid:monitor_id>/cancel/", DriftMonitorCancelEndpoint.as_view(), name="drift-monitor-cancel"),
    path("<uuid:monitor_id>/reference-url/", DriftMonitorReferenceURLEndpoint.as_view(), name="drift-monitor-reference-url"),
    path("<uuid:monitor_id>/reference-preview/", DriftMonitorReferencePreviewEndpoint.as_view(), name="drift-monitor-reference-preview"),
    path("<uuid:monitor_id>/runs/", DriftRunEndpoint.as_view(), name="drift-run"),
]

