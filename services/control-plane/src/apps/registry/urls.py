from django.urls import path

from apps.registry.artifacts.api import (
    ModelVersionReferenceDownloadEndpoint,
    ModelVersionReferencePreviewEndpoint,
    ModelVersionSupplementalArtifactsEndpoint,
)
from apps.registry.versions.api import ModelVersionDetailEndpoint

urlpatterns = [
    path("<uuid:version_id>/", ModelVersionDetailEndpoint.as_view(), name="version-detail"),
    path(
        "<uuid:version_id>/reference-data/download/",
        ModelVersionReferenceDownloadEndpoint.as_view(),
        name="version-reference-download",
    ),
    path(
        "<uuid:version_id>/supplemental-artifacts/",
        ModelVersionSupplementalArtifactsEndpoint.as_view(),
        name="version-supplemental-artifacts",
    ),
    path(
        "<uuid:version_id>/reference-data/preview/",
        ModelVersionReferencePreviewEndpoint.as_view(),
        name="version-reference-preview",
    ),
]
