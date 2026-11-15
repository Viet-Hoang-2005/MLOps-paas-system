from django.urls import path

from .workspace_views import (
    WorkspaceDetail,
    WorkspaceDownload,
    WorkspaceJobs,
    WorkspaceJob,
    WorkspaceList,
    WorkspaceRuns,
)
from .workspaces import WorkspaceEntriesEndpoint, WorkspaceEntryEndpoint, WorkspaceSecretEndpoint

urlpatterns = [
    path("", WorkspaceList.as_view()),
    path("<uuid:workspace_id>/", WorkspaceDetail.as_view()),
    path("<uuid:workspace_id>/runs/", WorkspaceRuns.as_view()),
    path("<uuid:workspace_id>/jobs/", WorkspaceJobs.as_view()),
    path("<uuid:workspace_id>/jobs/<uuid:job_id>/", WorkspaceJob.as_view()),
    path("<uuid:workspace_id>/entries/", WorkspaceEntriesEndpoint.as_view()),
    path("<uuid:workspace_id>/entries/<uuid:entry_id>/", WorkspaceEntryEndpoint.as_view()),
    path("<uuid:workspace_id>/secrets/<str:name>/", WorkspaceSecretEndpoint.as_view()),
    path("<uuid:workspace_id>/input/download/", WorkspaceDownload.as_view()),
]
