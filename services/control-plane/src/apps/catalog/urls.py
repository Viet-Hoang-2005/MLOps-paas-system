from django.urls import path

from apps.catalog.preview.api import (
    PreviewAttributesEndpoint,
    ProjectCreateUploadUrlsEndpoint,
    ProjectPreviewEndpoint,
    ProjectPreviewReferenceDownloadEndpoint,
    ProjectPreviewUploadUrlsEndpoint,
)
from apps.catalog.projects.api import ModelProjectDetailEndpoint, ModelProjectListCreateEndpoint, ProjectBuildEndpoint
from apps.catalog.running.api import RunningAttributesEndpoint, RunningSourceEndpoint
from apps.observability.runtime.api import ProductionDataEndpoint, RuntimeMetricsEndpoint
from apps.registry.versions.api import ProjectVersionListEndpoint

urlpatterns = [
    path("", ModelProjectListCreateEndpoint.as_view(), name="model-list"),
    path("preview/upload-urls/", ProjectCreateUploadUrlsEndpoint.as_view(), name="project-create-upload-urls"),
    path("<uuid:project_id>/", ModelProjectDetailEndpoint.as_view(), name="model-detail"),
    path("<uuid:project_id>/preview/", ProjectPreviewEndpoint.as_view(), name="project-preview"),
    path(
        "<uuid:project_id>/preview/reference-data/download/",
        ProjectPreviewReferenceDownloadEndpoint.as_view(),
        name="project-preview-reference-download",
    ),
    path(
        "<uuid:project_id>/preview/attributes/", PreviewAttributesEndpoint.as_view(), name="project-preview-attributes"
    ),
    path(
        "<uuid:project_id>/preview/upload-urls/",
        ProjectPreviewUploadUrlsEndpoint.as_view(),
        name="project-preview-upload-urls",
    ),
    path("<uuid:project_id>/running/source/", RunningSourceEndpoint.as_view(), name="project-running-source"),
    path(
        "<uuid:project_id>/running/attributes/", RunningAttributesEndpoint.as_view(), name="project-running-attributes"
    ),
    path("<uuid:project_id>/builds/", ProjectBuildEndpoint.as_view(), name="project-builds"),
    path("<uuid:project_id>/versions/", ProjectVersionListEndpoint.as_view(), name="project-versions"),
    path("<uuid:project_id>/production-data/", ProductionDataEndpoint.as_view(), name="model-production-data"),
    path("<uuid:project_id>/runtime-metrics/", RuntimeMetricsEndpoint.as_view(), name="runtime-metrics"),
]
