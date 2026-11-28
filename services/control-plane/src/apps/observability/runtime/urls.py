from django.urls import path

from apps.observability.runtime.api import ModelObservabilityEndpoint, RuntimeMetricsEndpoint

urlpatterns = [
    path("models/<uuid:project_id>/runtime-metrics/", RuntimeMetricsEndpoint.as_view(), name="runtime-metrics"),
    path("models/<uuid:project_id>/", ModelObservabilityEndpoint.as_view(), name="model-observability"),
]
