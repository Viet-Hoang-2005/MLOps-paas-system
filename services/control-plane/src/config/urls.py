from django.contrib import admin
from django.urls import include, path

from apps.deployment.builds.callbacks import BuildWebhookEndpoint
from apps.deployment.serving.callbacks import DeploymentWebhookEndpoint
from apps.deployment.urls import build_patterns, deployment_patterns, endpoint_patterns
from apps.drift.runs.callbacks import (
    AutomaticDriftWebhookEndpoint,
    DriftRunModelPackageURLEndpoint,
    DriftRunWebhookEndpoint,
)
from apps.mlflow.artifacts.api import MLflowArtifactsMultipartFallbackView, MLflowArtifactsProxyView
from apps.notifications.alerts import AlertWebhookEndpoint
from apps.observability.execution.callbacks import ArgoRuntimeStopEndpoint, ExecutionObservationEndpoint
from apps.observability.runtime.api import ProductionDataEndpoint
from apps.training.jobs.callbacks import (
    TrainingCancellationWebhookEndpoint,
    TrainingInputDownloadURLEndpoint,
    TrainingJobWebhookEndpoint,
    TrainingOutputUploadURLEndpoint,
    TrainingRuntimeConfigEndpoint,
)
from common.api.csv_uploads import CSVUploadURLEndpoint

urlpatterns = [
    path("internal/executions/<str:kind>/<uuid:public_id>/observations/", ExecutionObservationEndpoint.as_view()),
    path("internal/executions/<str:kind>/<uuid:public_id>/stops/", ArgoRuntimeStopEndpoint.as_view()),
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.auth.urls")),
    path("api/api-keys/", include("apps.access.urls")),
    path("api/csv-upload-urls/<str:purpose>/<uuid:resource_id>/", CSVUploadURLEndpoint.as_view()),
    path("api/2.0/mlflow/", include("apps.mlflow.urls")),
    # MLflow Root Artifact Proxy routes (for root or non-prefixed tracking URIs)
    path("api/2.0/mlflow-artifacts/artifacts/<path:subpath>", MLflowArtifactsProxyView.as_view()),
    path("api/2.0/mlflow-artifacts/artifacts", MLflowArtifactsProxyView.as_view()),
    path("mlflow-artifacts/artifacts/<path:subpath>", MLflowArtifactsProxyView.as_view()),
    path("mlflow-artifacts/artifacts", MLflowArtifactsProxyView.as_view()),
    path("api/2.0/mlflow-artifacts/mpu/<path:subpath>", MLflowArtifactsMultipartFallbackView.as_view()),
    path("mlflow-artifacts/mpu/<path:subpath>", MLflowArtifactsMultipartFallbackView.as_view()),
    path(
        "api/models/<uuid:project_id>/production-data/",
        ProductionDataEndpoint.as_view(),
        name="model-production-data",
    ),
    path("api/models/", include("apps.catalog.urls")),
    path("api/registry/", include("apps.registry.urls")),
    path("api/training-jobs/", include("apps.training.urls")),
    path("api/training-workspaces/", include("apps.training.workspace.urls")),
    path("api/builds/", include((build_patterns, "builds"))),
    path("api/deployments/", include((deployment_patterns, "deployments"))),
    path("api/endpoints/", include((endpoint_patterns, "endpoints"))),
    path("api/drift-monitors/", include("apps.drift.urls")),
    path("api/observability/", include("apps.observability.runtime.urls")),
    path("health/", include("apps.observability.urls")),
    path("internal/webhooks/builds/<uuid:build_id>/", BuildWebhookEndpoint.as_view()),
    path("internal/webhooks/deployments/<uuid:deployment_id>/", DeploymentWebhookEndpoint.as_view()),
    path("internal/webhooks/training-jobs/<uuid:job_id>/", TrainingJobWebhookEndpoint.as_view()),
    path(
        "internal/webhooks/training-jobs/<uuid:job_id>/cancellation/",
        TrainingCancellationWebhookEndpoint.as_view(),
    ),
    path("internal/training-jobs/<uuid:job_id>/output-upload-url/", TrainingOutputUploadURLEndpoint.as_view()),
    path("internal/training-jobs/<uuid:job_id>/input-download-urls/", TrainingInputDownloadURLEndpoint.as_view()),
    path("internal/training-jobs/<uuid:job_id>/runtime-config/", TrainingRuntimeConfigEndpoint.as_view()),
    path("api/notifications/", include("apps.notifications.urls")),
    path("internal/webhooks/drift-runs/<uuid:run_id>/", DriftRunWebhookEndpoint.as_view()),
    path("internal/drift-runs/<uuid:run_id>/model-package-url/", DriftRunModelPackageURLEndpoint.as_view()),
    path("internal/webhooks/automatic-drift/", AutomaticDriftWebhookEndpoint.as_view()),
    path("internal/webhooks/alerts/", AlertWebhookEndpoint.as_view()),
]
