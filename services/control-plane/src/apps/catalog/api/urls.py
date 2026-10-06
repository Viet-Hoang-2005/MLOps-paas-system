from django.urls import path

from .endpoints import (
    ModelProjectDetailEndpoint,
    ModelProjectListCreateEndpoint,
    ProjectBuildEndpoint,
    ProjectPreviewEndpoint,
    ProjectPreviewReferencePreviewEndpoint,
    RunningSourceEndpoint,
    TrainingProjectCreateEndpoint,
    WorkspaceFilesEndpoint,
)

urlpatterns = [
    path("", ModelProjectListCreateEndpoint.as_view(), name="model-list"),
    path("training-projects/", TrainingProjectCreateEndpoint.as_view(), name="training-project-create"),
    path("<uuid:project_id>/", ModelProjectDetailEndpoint.as_view(), name="model-detail"),
    path("<uuid:project_id>/preview/", ProjectPreviewEndpoint.as_view(), name="project-preview"),
    path(
        "<uuid:project_id>/preview/reference-preview/",
        ProjectPreviewReferencePreviewEndpoint.as_view(),
        name="project-preview-reference-preview",
    ),
    path("<uuid:project_id>/running-source/", RunningSourceEndpoint.as_view(), name="project-running-source"),
    path("<uuid:project_id>/builds/", ProjectBuildEndpoint.as_view(), name="project-builds"),
    path("<uuid:project_id>/workspace/<str:kind>/files/", WorkspaceFilesEndpoint.as_view(), name="workspace-files"),
]

