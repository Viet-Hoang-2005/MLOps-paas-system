from django.urls import path

from .endpoints import (
    ModelDraftAssetCompleteEndpoint,
    ModelDraftAssetDeleteEndpoint,
    ModelDraftAssetUploadUrlEndpoint,
    ModelDraftBuildEndpoint,
    ModelDraftDetailEndpoint,
    ModelDraftDiscardEndpoint,
    ModelDraftLoadVersionEndpoint,
    ModelDraftSaveEndpoint,
    ModelProjectDetailEndpoint,
    ModelProjectListCreateEndpoint,
    ModelProjectOverviewEndpoint,
    ProjectBuildEndpoint,
)

urlpatterns = [
    path("", ModelProjectListCreateEndpoint.as_view(), name="model-list"),
    path("<uuid:project_id>/", ModelProjectDetailEndpoint.as_view(), name="model-detail"),
    path("<uuid:project_id>/overview/", ModelProjectOverviewEndpoint.as_view(), name="model-overview"),
    path("<uuid:project_id>/draft/", ModelDraftDetailEndpoint.as_view(), name="model-draft-detail"),
    path("<uuid:project_id>/draft/save/", ModelDraftSaveEndpoint.as_view(), name="model-draft-save"),
    path("<uuid:project_id>/draft/discard/", ModelDraftDiscardEndpoint.as_view(), name="model-draft-discard"),
    path(
        "<uuid:project_id>/draft/assets/upload-url/",
        ModelDraftAssetUploadUrlEndpoint.as_view(),
        name="model-draft-asset-upload-url",
    ),
    path(
        "<uuid:project_id>/draft/assets/complete/",
        ModelDraftAssetCompleteEndpoint.as_view(),
        name="model-draft-asset-complete",
    ),
    path(
        "<uuid:project_id>/draft/assets/<str:kind>/",
        ModelDraftAssetDeleteEndpoint.as_view(),
        name="model-draft-asset-delete",
    ),
    path("<uuid:project_id>/draft/build/", ModelDraftBuildEndpoint.as_view(), name="model-draft-build"),
    path(
        "<uuid:project_id>/draft/load-version/",
        ModelDraftLoadVersionEndpoint.as_view(),
        name="model-draft-load-version",
    ),
    path("<uuid:project_id>/builds/", ProjectBuildEndpoint.as_view(), name="project-builds"),
]
