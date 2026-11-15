from django.urls import path

from .endpoints import (
    TrainingJobBuildEndpoint,
    TrainingJobCancelEndpoint,
    TrainingJobDetailEndpoint,
    TrainingJobEventsEndpoint,
    TrainingJobInputEndpoint,
    TrainingJobListEndpoint,
    TrainingJobLogsEndpoint,
    TrainingJobModelOutputEndpoint,
    TrainingJobOutputsEndpoint,
    TrainingJobProjectEndpoint,
    TrainingJobReferencePreviewEndpoint,
    TrainingOutputDownloadEndpoint,
    TrainingRuntimeCapabilitiesEndpoint,
    TrainingUsageEndpoint,
    TrainingWorkspaceDownloadEndpoint,
)
from .metrics_endpoints import (
    TrainingJobExperimentMetricsEndpoint,
    TrainingJobRuntimeMetricsEndpoint,
    TrainingJobsCompareEndpoint,
)

urlpatterns = [
    path(
        "<uuid:job_id>/input/download/",
        TrainingWorkspaceDownloadEndpoint.as_view(),
        {"area": "input"},
        name="training-input-download",
    ),
    path(
        "<uuid:job_id>/outputs/download/",
        TrainingWorkspaceDownloadEndpoint.as_view(),
        {"area": "output"},
        name="training-outputs-download",
    ),
    path("", TrainingJobListEndpoint.as_view(), name="training-job-list"),
    path("compare/", TrainingJobsCompareEndpoint.as_view(), name="training-jobs-compare"),
    path("usage/", TrainingUsageEndpoint.as_view(), name="training-usage"),
    path("<uuid:job_id>/", TrainingJobDetailEndpoint.as_view(), name="training-job-detail"),
    path(
        "<uuid:job_id>/experiment-metrics/",
        TrainingJobExperimentMetricsEndpoint.as_view(),
        name="training-job-experiment-metrics",
    ),
    path(
        "<uuid:job_id>/runtime-metrics/",
        TrainingJobRuntimeMetricsEndpoint.as_view(),
        name="training-job-runtime-metrics",
    ),
    path("<uuid:job_id>/project/", TrainingJobProjectEndpoint.as_view(), name="training-job-project"),
    path("<uuid:job_id>/cancel/", TrainingJobCancelEndpoint.as_view(), name="training-job-cancel"),
    path("<uuid:job_id>/events/", TrainingJobEventsEndpoint.as_view(), name="training-job-events"),
    path("<uuid:job_id>/logs/", TrainingJobLogsEndpoint.as_view(), name="training-job-logs"),
    path("<uuid:job_id>/input/", TrainingJobInputEndpoint.as_view(), name="training-job-input"),
    path(
        "<uuid:job_id>/outputs/<uuid:output_id>/download/",
        TrainingOutputDownloadEndpoint.as_view(),
        name="training-output-download",
    ),
    path("<uuid:job_id>/build/", TrainingJobBuildEndpoint.as_view(), name="training-job-build"),
    path("<uuid:job_id>/model-output/", TrainingJobModelOutputEndpoint.as_view(), name="training-job-model-output"),
    path(
        "<uuid:job_id>/reference-preview/",
        TrainingJobReferencePreviewEndpoint.as_view(),
        name="training-job-reference-preview",
    ),
    path("<uuid:job_id>/outputs/", TrainingJobOutputsEndpoint.as_view(), name="training-job-outputs"),
    path(
        "runtime-capabilities/",
        TrainingRuntimeCapabilitiesEndpoint.as_view(),
        name="training-runtime-capabilities",
    ),
]
