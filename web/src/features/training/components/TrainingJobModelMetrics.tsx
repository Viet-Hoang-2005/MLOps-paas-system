import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Activity, Sliders, TrendingUp } from "lucide-react";

import { getTrainingJobMetricsHistory } from "@/features/training/api/trainingApi";
import { Chart } from "@/shared/components/Chart";
import { formatNumber } from "@/shared/i18n/formatters";

interface TrainingJobModelMetricsProps {
  jobId: string;
  jobStatus: string;
}

export function TrainingJobModelMetrics({
  jobId,
  jobStatus,
}: TrainingJobModelMetricsProps) {
  const { t, i18n } = useTranslation("training");
  const isRunning = jobStatus === "running";

  const { data, isLoading } = useQuery({
    queryKey: ["training-job-metrics-history", jobId],
    queryFn: () => getTrainingJobMetricsHistory(jobId),
    refetchInterval: isRunning ? 3000 : false,
  });

  const number = (value: number) =>
    formatNumber(value, i18n.language, { maximumFractionDigits: 6 });

  if (isLoading) {
    return (
      <div className="flex h-48 items-center justify-center rounded-surface border border-border bg-surface">
        <p className="text-style-caption text-color-muted-foreground animate-pulse">
          {t("detail.metricsPage.waitingRunner", "Loading experiment tracking data...")}
        </p>
      </div>
    );
  }

  const series = data?.series ?? [];
  const params = Object.entries(data?.params ?? {});
  const metricsSummary = Object.entries(data?.metrics_summary ?? {});

  const hasAnyData = series.length > 0 || params.length > 0 || metricsSummary.length > 0;

  if (!hasAnyData) {
    return (
      <div className="rounded-surface border border-dashed border-border bg-muted/40 p-8 text-center">
        <TrendingUp className="mx-auto mb-3 h-8 w-8 text-color-muted-foreground/60" />
        <p className="text-style-body-strong text-color-foreground">
          {t("detail.metricsPage.noModelMetricsTitle", "No Experiment Tracking Logs Yet")}
        </p>
        <p className="mt-1 text-style-caption text-color-muted-foreground">
          {t(
            "detail.metricsPage.noModelMetricsHint",
            "Call mlflow.autolog() or mlflow.log_metric() in your script to stream realtime training loss curves here."
          )}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Hyperparameters section */}
      {params.length > 0 && (
        <div className="rounded-surface border border-border bg-surface p-5 shadow-sm">
          <div className="mb-3 flex items-center gap-2 border-b border-border pb-3">
            <Sliders className="h-4 w-4 text-color-primary" />
            <h4 className="text-style-overline uppercase text-color-foreground">
              {t("detail.metricsPage.hyperparameters", "Hyperparameters")}
            </h4>
          </div>
          <div className="flex flex-wrap gap-2">
            {params.map(([key, val]) => (
              <span
                key={key}
                className="inline-flex items-center gap-1.5 rounded-compact border border-border bg-muted px-2.5 py-1 font-mono text-style-caption"
              >
                <span className="font-bold text-color-foreground">{key}:</span>
                <span className="text-color-muted-foreground">{val}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Summary Metrics Cards */}
      {metricsSummary.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {metricsSummary.map(([key, val]) => (
            <div
              key={key}
              className="rounded-surface border border-border bg-surface p-4 shadow-sm"
            >
              <p className="truncate text-style-caption font-bold uppercase text-color-muted-foreground">
                {key}
              </p>
              <p className="mt-1 text-style-page-title font-bold text-color-foreground">
                {typeof val === "number" ? number(val) : String(val)}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Realtime / Step-by-Step Training Curves */}
      {series.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="flex items-center gap-2 text-style-overline uppercase text-color-foreground">
              <Activity className="h-4 w-4 text-color-info" />
              {t("detail.metricsPage.trainingCurves", "Training & Validation Curves (Step History)")}
            </h4>
            {isRunning && (
              <span className="flex items-center gap-1.5 text-style-caption font-bold text-color-success">
                <span className="h-2 w-2 rounded-full bg-success animate-ping" />
                {t("detail.metricsPage.liveStreaming", "Live streaming")}
              </span>
            )}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {series.map((item) => {
              const chartData = item.points.map((pt) => ({
                timestamp: pt.step,
                value: pt.value,
              }));

              return (
                <div
                  key={item.name}
                  className="space-y-3 rounded-surface border border-border bg-surface p-5 shadow-sm"
                >
                  <div className="flex items-center justify-between">
                    <h5 className="font-mono text-style-body-strong text-color-foreground">
                      {item.name}
                    </h5>
                    <span className="text-style-caption text-color-muted-foreground">
                      {item.points.length} {t("detail.metricsPage.steps", "steps")}
                    </span>
                  </div>
                  <Chart
                    allowNegative
                    data={chartData}
                    height={180}
                    timeFormatter={(step) => `${t("detail.metricsPage.step", "Step")} ${number(step)}`}
                    valueFormatter={number}
                    emptyText={t("detail.metricsPage.insufficientPoints", "Insufficient data points")}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
