from django.urls import path

from .endpoints import (
    DriftMonitorDetailEndpoint,
    DriftMonitorListCreateEndpoint,
    DriftRunEndpoint,
    DriftRunLogsEndpoint,
    DriftRunReportURLEndpoint,
)

urlpatterns = [
    path("", DriftMonitorListCreateEndpoint.as_view(), name="drift-monitor-list"),
    path("runs/<uuid:run_id>/logs/", DriftRunLogsEndpoint.as_view(), name="drift-run-logs"),
    path("runs/<uuid:run_id>/report-url/", DriftRunReportURLEndpoint.as_view(), name="drift-run-report-url"),
    path("<uuid:monitor_id>/", DriftMonitorDetailEndpoint.as_view(), name="drift-monitor-detail"),
    path("<uuid:monitor_id>/runs/", DriftRunEndpoint.as_view(), name="drift-run"),
]
