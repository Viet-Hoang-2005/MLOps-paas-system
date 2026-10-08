from django.urls import path

from .endpoints import (
    ModelProjectDetailEndpoint,
    ModelProjectListCreateEndpoint,
    ProjectBuildEndpoint,
    ProjectCreateUploadUrlsEndpoint,
    ProjectPreviewEndpoint,
    ProjectPreviewReferencePreviewEndpoint,
    ProjectPreviewUploadUrlsEndpoint,
    PreviewAttributesEndpoint,
    RunningAttributesEndpoint,
    RunningLabelMappingEndpoint,
    RunningSourceEndpoint,
    TrainingProjectCreateEndpoint,
    WorkspaceFilesEndpoint,
)

urlpatterns = [
    path("", ModelProjectListCreateEndpoint.as_view(), name="model-list"),
    path("training-projects/", TrainingProjectCreateEndpoint.as_view(), name="training-project-create"),
    path("preview/upload-urls/", ProjectCreateUploadUrlsEndpoint.as_view(), name="project-create-upload-urls"),
    path("<uuid:project_id>/", ModelProjectDetailEndpoint.as_view(), name="model-detail"),
    path("<uuid:project_id>/preview/", ProjectPreviewEndpoint.as_view(), name="project-preview"),
    path("<uuid:project_id>/preview/attributes/", PreviewAttributesEndpoint.as_view(), name="project-preview-attributes"),
    path(
        "<uuid:project_id>/preview/upload-urls/",
        ProjectPreviewUploadUrlsEndpoint.as_view(),
        name="project-preview-upload-urls",
    ),
    path(
        "<uuid:project_id>/preview/reference-preview/",
        ProjectPreviewReferencePreviewEndpoint.as_view(),
        name="project-preview-reference-preview",
    ),
    path("<uuid:project_id>/running-source/", RunningSourceEndpoint.as_view(), name="project-running-source"),
    path("<uuid:project_id>/running-attributes/", RunningAttributesEndpoint.as_view(), name="project-running-attributes"),
    path("<uuid:project_id>/label-mapping/", RunningLabelMappingEndpoint.as_view(), name="project-label-mapping"),
    path("<uuid:project_id>/builds/", ProjectBuildEndpoint.as_view(), name="project-builds"),
    path("<uuid:project_id>/workspace/<str:kind>/files/", WorkspaceFilesEndpoint.as_view(), name="workspace-files"),
]
