from django.urls import path

from .endpoints import (
    ModelVersionDetailEndpoint,
    ModelVersionReferenceDownloadEndpoint,
    ModelVersionReferencePreviewEndpoint,
    ModelVersionSupplementalArtifactsEndpoint,
    ProjectVersionListCreateEndpoint,
)

urlpatterns = [
    path("models/<uuid:project_id>/versions/", ProjectVersionListCreateEndpoint.as_view(), name="project-versions"),
    path("versions/<uuid:version_id>/", ModelVersionDetailEndpoint.as_view(), name="version-detail"),
    path(
        "versions/<uuid:version_id>/reference-download/",
        ModelVersionReferenceDownloadEndpoint.as_view(),
        name="version-reference-download",
    ),
    path(
        "versions/<uuid:version_id>/supplemental-artifacts/",
        ModelVersionSupplementalArtifactsEndpoint.as_view(),
        name="version-supplemental-artifacts",
    ),
    path(
        "versions/<uuid:version_id>/reference-preview/",
        ModelVersionReferencePreviewEndpoint.as_view(),
        name="version-reference-preview",
    ),
]
