from django.urls import path

from .workspaces import WorkspaceDetailEndpoint, WorkspaceEntriesEndpoint, WorkspaceEntryEndpoint, WorkspaceListEndpoint, WorkspaceSecretEndpoint

urlpatterns = [
    path("", WorkspaceListEndpoint.as_view(), name="training-workspace-list"),
    path("<uuid:workspace_id>/", WorkspaceDetailEndpoint.as_view(), name="training-workspace-detail"),
    path("<uuid:workspace_id>/entries/", WorkspaceEntriesEndpoint.as_view(), name="training-workspace-entries"),
    path("<uuid:workspace_id>/entries/<uuid:entry_id>/", WorkspaceEntryEndpoint.as_view(), name="training-workspace-entry"),
    path("<uuid:workspace_id>/secrets/<str:name>/", WorkspaceSecretEndpoint.as_view(), name="training-workspace-secret"),
]
