from django.urls import path

from apps.training.jobs.api import (
    TrainingJobBuildEndpoint,
    TrainingJobCancelEndpoint,
    TrainingJobDetailEndpoint,
    TrainingJobEventsEndpoint,
    TrainingJobInputEndpoint,
    TrainingJobListEndpoint,
    TrainingJobLogsEndpoint,
    TrainingJobProjectEndpoint,
)
from apps.training.jobs.metrics_api import (
    TrainingJobExperimentMetricsEndpoint,
    TrainingJobRuntimeMetricsEndpoint,
    TrainingJobsCompareEndpoint,
)
from apps.training.outputs.api import (
    TrainingJobModelOutputEndpoint,
    TrainingJobOutputsEndpoint,
    TrainingJobReferencePreviewEndpoint,
    TrainingOutputDownloadEndpoint,
    TrainingWorkspaceDownloadEndpoint,
)
from apps.training.resources.api import TrainingRuntimeCapabilitiesEndpoint, TrainingUsageEndpoint

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
        "<uuid:job_id>/reference-data/preview/",
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
