from django.urls import path

from .endpoints import (
    ModelProjectDetailEndpoint,
    ModelProjectListCreateEndpoint,
    ProjectBuildEndpoint,
    WorkspaceFilesEndpoint,
)

urlpatterns = [
    path("", ModelProjectListCreateEndpoint.as_view(), name="model-list"),
    path("<uuid:project_id>/", ModelProjectDetailEndpoint.as_view(), name="model-detail"),
    path("<uuid:project_id>/builds/", ProjectBuildEndpoint.as_view(), name="project-builds"),
    path("<uuid:project_id>/workspace/<str:kind>/files/", WorkspaceFilesEndpoint.as_view(), name="workspace-files"),
]
