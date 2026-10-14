from django.urls import path
from .mlflow_compat import (
    MLflowArtifactsListView,
    MLflowArtifactsMultipartFallbackView,
    MLflowArtifactsProxyView,
    MLflowArtifactsUploadUrlView,
    MLflowExperimentsCreateView,
    MLflowExperimentsGetByNameView,
    MLflowExperimentsGetView,
    MLflowMetricsGetHistoryView,
    MLflowRunsCreateView,
    MLflowRunsGetView,
    MLflowRunsLogBatchView,
    MLflowRunsLogMetricView,
    MLflowRunsLogParameterView,
    MLflowRunsSetTagView,
    MLflowRunsUpdateView,
)

urlpatterns = [
    # Experiments
    path("experiments/get-by-name", MLflowExperimentsGetByNameView.as_view(), name="mlflow-exp-get-by-name"),
    path("experiments/create", MLflowExperimentsCreateView.as_view(), name="mlflow-exp-create"),
    path("experiments/get", MLflowExperimentsGetView.as_view(), name="mlflow-exp-get"),
    # Runs
    path("runs/create", MLflowRunsCreateView.as_view(), name="mlflow-runs-create"),
    path("runs/log-batch", MLflowRunsLogBatchView.as_view(), name="mlflow-runs-log-batch"),
    path("runs/log-metric", MLflowRunsLogMetricView.as_view(), name="mlflow-runs-log-metric"),
    path("runs/log-parameter", MLflowRunsLogParameterView.as_view(), name="mlflow-runs-log-parameter"),
    path("runs/set-tag", MLflowRunsSetTagView.as_view(), name="mlflow-runs-set-tag"),
    path("runs/update", MLflowRunsUpdateView.as_view(), name="mlflow-runs-update"),
    path("runs/get", MLflowRunsGetView.as_view(), name="mlflow-runs-get"),
    # Metrics
    path("metrics/get-history", MLflowMetricsGetHistoryView.as_view(), name="mlflow-metrics-get-history"),
    # Artifacts (standard MLflow and proxy routes)
    path("artifacts/list", MLflowArtifactsListView.as_view(), name="mlflow-artifacts-list"),
    path("artifacts/upload-url", MLflowArtifactsUploadUrlView.as_view(), name="mlflow-artifacts-upload-url"),
    path("api/2.0/mlflow-artifacts/artifacts/<path:subpath>", MLflowArtifactsProxyView.as_view(), name="mlflow-artifacts-proxy-subpath"),
    path("api/2.0/mlflow-artifacts/artifacts", MLflowArtifactsProxyView.as_view(), name="mlflow-artifacts-proxy-root"),
    path("mlflow-artifacts/artifacts/<path:subpath>", MLflowArtifactsProxyView.as_view(), name="mlflow-artifacts-proxy-alt-subpath"),
    path("mlflow-artifacts/artifacts", MLflowArtifactsProxyView.as_view(), name="mlflow-artifacts-proxy-alt-root"),
    path("api/2.0/mlflow-artifacts/mpu/<path:subpath>", MLflowArtifactsMultipartFallbackView.as_view(), name="mlflow-mpu-fallback"),
    path("mlflow-artifacts/mpu/<path:subpath>", MLflowArtifactsMultipartFallbackView.as_view(), name="mlflow-mpu-fallback-alt"),
]

