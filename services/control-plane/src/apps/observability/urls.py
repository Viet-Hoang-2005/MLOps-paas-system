from django.urls import path

from apps.observability.health import LiveEndpoint, MetricsEndpoint, ReadyEndpoint

urlpatterns = [
    path("live", LiveEndpoint.as_view()),
    path("ready", ReadyEndpoint.as_view()),
    path("metrics", MetricsEndpoint.as_view()),
]
