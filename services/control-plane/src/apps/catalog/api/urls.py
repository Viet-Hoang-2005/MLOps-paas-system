from django.urls import path

from .endpoints import (
    ModelProjectDetailEndpoint,
    ModelProjectListCreateEndpoint,
    ProjectBuildEndpoint,
    ProjectBuildUploadUrlEndpoint,
    WorkspaceFilesEndpoint,
)

urlpatterns = [
    path("", ModelProjectListCreateEndpoint.as_view(), name="model-list"),
    path("<uuid:project_id>/", ModelProjectDetailEndpoint.as_view(), name="model-detail"),
    path("<uuid:project_id>/builds/upload-url/", ProjectBuildUploadUrlEndpoint.as_view(), name="project-build-upload-url"),
    path("<uuid:project_id>/builds/", ProjectBuildEndpoint.as_view(), name="project-builds"),
    path("<uuid:project_id>/workspace/<str:kind>/files/", WorkspaceFilesEndpoint.as_view(), name="workspace-files"),
]
