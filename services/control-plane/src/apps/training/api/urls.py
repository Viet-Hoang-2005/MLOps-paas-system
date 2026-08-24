from django.urls import path

from .endpoints import (
    TrainingJobBuildEndpoint,
    TrainingJobCancelEndpoint,
    TrainingJobDetailEndpoint,
    TrainingJobDownloadEndpoint,
    TrainingJobEventsEndpoint,
    TrainingJobListCreateEndpoint,
    TrainingJobLogsEndpoint,
    TrainingJobOutputsEndpoint,
    TrainingJobSubmitEndpoint,
    TrainingRuntimeCapabilitiesEndpoint,
)

urlpatterns = [
    path("", TrainingJobListCreateEndpoint.as_view(), name="training-job-list"),
    path("<uuid:job_id>/", TrainingJobDetailEndpoint.as_view(), name="training-job-detail"),
    path("<uuid:job_id>/submit/", TrainingJobSubmitEndpoint.as_view(), name="training-job-submit"),
    path("<uuid:job_id>/cancel/", TrainingJobCancelEndpoint.as_view(), name="training-job-cancel"),
    path("<uuid:job_id>/events/", TrainingJobEventsEndpoint.as_view(), name="training-job-events"),
    path("<uuid:job_id>/logs/", TrainingJobLogsEndpoint.as_view(), name="training-job-logs"),
    path("<uuid:job_id>/download/", TrainingJobDownloadEndpoint.as_view(), name="training-job-download"),
    path("<uuid:job_id>/build/", TrainingJobBuildEndpoint.as_view(), name="training-job-build"),
    path("<uuid:job_id>/outputs/", TrainingJobOutputsEndpoint.as_view(), name="training-job-outputs"),
    path(
        "runtime-capabilities/",
        TrainingRuntimeCapabilitiesEndpoint.as_view(),
        name="training-runtime-capabilities",
    ),
]
