from django.urls import path

from .endpoints import (
    AliasPredictionEndpoint,
    ModelVersionDetailEndpoint,
    ModelVersionReferencePreviewEndpoint,
    ModelVersionSupplementalArtifactsEndpoint,
    ProjectAliasListCreateEndpoint,
    ProjectVersionListCreateEndpoint,
    VersionSmokeTestEndpoint,
)

urlpatterns = [
    path("models/<uuid:project_id>/versions/", ProjectVersionListCreateEndpoint.as_view(), name="project-versions"),
    path("versions/<uuid:version_id>/", ModelVersionDetailEndpoint.as_view(), name="version-detail"),
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
    path("versions/<uuid:version_id>/smoke-test/", VersionSmokeTestEndpoint.as_view(), name="version-smoke-test"),
    path("models/<uuid:project_id>/aliases/", ProjectAliasListCreateEndpoint.as_view(), name="project-aliases"),
    path(
        "models/<uuid:project_id>/aliases/<str:alias_name>/predict/",
        AliasPredictionEndpoint.as_view(),
        name="alias-predict",
    ),
]
