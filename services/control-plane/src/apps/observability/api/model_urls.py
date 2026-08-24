from django.urls import path

from .endpoints import ModelObservabilityEndpoint

urlpatterns = [
    path("models/<uuid:project_id>/", ModelObservabilityEndpoint.as_view(), name="model-observability"),
]
