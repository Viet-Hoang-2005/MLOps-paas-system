from django.urls import path

from apps.drift.monitors.api import (
    DriftMonitorCancelEndpoint,
    DriftMonitorDetailEndpoint,
    DriftMonitorListCreateEndpoint,
    DriftMonitorReferenceDownloadEndpoint,
    DriftMonitorReferenceReadURLEndpoint,
)
from apps.drift.runs.api import DriftRunEndpoint

urlpatterns = [
    path("", DriftMonitorListCreateEndpoint.as_view(), name="drift-monitor-list"),
    path("<uuid:monitor_id>/", DriftMonitorDetailEndpoint.as_view(), name="drift-monitor-detail"),
    path("<uuid:monitor_id>/cancel/", DriftMonitorCancelEndpoint.as_view(), name="drift-monitor-cancel"),
    path(
        "<uuid:monitor_id>/reference-data/read-url/",
        DriftMonitorReferenceReadURLEndpoint.as_view(),
        name="drift-monitor-reference-read-url",
    ),
    path(
        "<uuid:monitor_id>/reference-data/download/",
        DriftMonitorReferenceDownloadEndpoint.as_view(),
        name="drift-monitor-reference-download",
    ),
    path("<uuid:monitor_id>/runs/", DriftRunEndpoint.as_view(), name="drift-run"),
]
