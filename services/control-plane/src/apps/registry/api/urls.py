from django.urls import path

from .endpoints import (
    AliasPredictionEndpoint,
    ModelVersionDetailEndpoint,
    ProjectAliasListCreateEndpoint,
    ProjectVersionListCreateEndpoint,
    VersionSmokeTestEndpoint,
)

urlpatterns = [
    path("models/<uuid:project_id>/versions/", ProjectVersionListCreateEndpoint.as_view(), name="project-versions"),
    path("versions/<uuid:version_id>/", ModelVersionDetailEndpoint.as_view(), name="version-detail"),
    path("versions/<uuid:version_id>/smoke-test/", VersionSmokeTestEndpoint.as_view(), name="version-smoke-test"),
    path("models/<uuid:project_id>/aliases/", ProjectAliasListCreateEndpoint.as_view(), name="project-aliases"),
    path(
        "models/<uuid:project_id>/aliases/<str:alias_name>/predict/",
        AliasPredictionEndpoint.as_view(),
        name="alias-predict",
    ),
]
