from django.urls import path

from .views import (
    MLflowArtifactsListView,
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
    # Artifacts
    path("artifacts/list", MLflowArtifactsListView.as_view(), name="mlflow-artifacts-list"),
]
