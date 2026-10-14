import { formatDateTime } from "@/shared/i18n/formatters";
import { formatNumber } from "@/shared/i18n/formatters";
import type { ReactNode } from "react";
import { Activity, Cpu, HardDrive, RefreshCw, Rocket } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useTrainingJobDetailContext } from "@/features/training/trainingJobDetailContext";
import { TrainingJobModelMetrics } from "@/features/training/components/TrainingJobModelMetrics";

export default function TrainingJobMetricsPage() {
  const { t, i18n } = useTranslation("training");
  const formatMetricPercent = (value: number) =>
    `${formatNumber(Math.round(value), i18n.language)}%`;
  const formatMegabytes = (megabytes: number) =>
    megabytes >= 1024
      ? `${formatNumber(megabytes / 1024, i18n.language, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GB`
      : `${formatNumber(Math.round(megabytes), i18n.language)} MB`;
  const {
    job,
    activeStatuses,
    metrics,
    loadingMetrics,
    refreshingSection,
    refreshMetrics,
  } = useTrainingJobDetailContext();

  const latest = metrics?.latest;
  const highCpu = latest?.cpu_percent != null && latest.cpu_percent > 85;
  const highRam = latest?.memory_percent != null && latest.memory_percent > 85;
  const memoryValue =
    latest?.memory_percent != null
      ? formatMetricPercent(latest.memory_percent)
      : latest?.memory_used_mb != null
        ? t("detail.metricsPage.memoryUsed", {
            memory: formatMegabytes(latest.memory_used_mb),
          })
        : "-";
  const memoryDetail =
    latest?.memory_used_mb != null && latest?.memory_limit_mb != null
      ? `${formatMegabytes(latest.memory_used_mb)} / ${formatMegabytes(
          latest.memory_limit_mb,
        )}`
      : latest?.memory_used_mb != null
        ? t("detail.metricsPage.memoryUsed", {
            memory: formatMegabytes(latest.memory_used_mb),
          })
        : metrics?.message || t("detail.metricsPage.waitingRunner");
  const gpuValue =
    latest?.gpu_available && latest.gpu_percent != null
      ? formatMetricPercent(latest.gpu_percent)
      : t("detail.metricsPage.gpuUnavailable");
  const gpuDetail =
    latest?.gpu_available &&
    latest.gpu_memory_used_mb != null &&
    latest.gpu_memory_total_mb != null
      ? `${formatMegabytes(latest.gpu_memory_used_mb)} / ${formatMegabytes(
          latest.gpu_memory_total_mb,
        )}`
      : t("detail.metricsPage.noGpu");
  const refreshing = loadingMetrics || refreshingSection === "metrics";

  return (
    <div className="animate-in space-y-6 fade-in duration-300">
      {/* 1. Experiment Tracking: Loss Curves, Hyperparameters, Summary */}
      <section className="space-y-4">
        <TrainingJobModelMetrics jobId={job.id} jobStatus={job.status} />
      </section>

      {/* 2. Container System Resources: CPU, RAM, GPU */}
      <section className="rounded-surface border border-border bg-surface p-6 shadow-sm">
        <div className="mb-6 flex items-center justify-between gap-3 border-b border-border pb-4">
          <p className="flex items-center gap-2 text-style-overline uppercase text-color-foreground">
            <Activity className="h-4 w-4 text-color-info" />
            {t("detail.metricsPage.title")}
          </p>
          <div className="flex items-center gap-3">
            <span className="text-style-caption-strong text-color-muted-foreground">
              {latest?.timestamp
                ? t("detail.metricsPage.sampled", {
                    time: formatDateTime(latest.timestamp, i18n.language, {
                      timeStyle: "medium",
                    }),
                  })
                : activeStatuses.includes(job.status)
                  ? t("detail.metricsPage.starting")
                  : t("detail.metricsPage.pending")}
            </span>
            <button
              type="button"
              onClick={() => void refreshMetrics()}
              disabled={refreshing}
              className="flex h-7 items-center gap-1.5 rounded-compact border border-border bg-muted px-2.5 text-style-caption font-bold text-color-muted-foreground transition-colors hover:bg-muted disabled:opacity-50"
            >
              <RefreshCw
                className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`}
              />
              {t("detail.metricsPage.refresh")}
            </button>
          </div>
        </div>

        {metrics?.metrics_available ? (
          <div className="grid gap-4 sm:grid-cols-3">
            <MetricCell
              icon={<Cpu className="h-3.5 w-3.5" />}
              label={t("detail.metricsPage.cpu")}
              value={
                latest?.cpu_percent == null
                  ? "-"
                  : formatMetricPercent(latest.cpu_percent)
              }
              detail={
                latest?.cpu_limit_cores
                  ? t("detail.metricsPage.cpuLimit", {
                      count: latest.cpu_limit_cores,
                    })
                  : t("detail.metricsPage.cpuUsage")
              }
              warning={highCpu}
              progress={latest?.cpu_percent}
              progressColor={highCpu ? "bg-warning" : "bg-success"}
            />
            <MetricCell
              icon={<HardDrive className="h-3.5 w-3.5" />}
              label={t("detail.metricsPage.ram")}
              value={memoryValue}
              detail={memoryDetail}
              warning={highRam}
              progress={latest?.memory_percent}
              progressColor={highRam ? "bg-danger" : "bg-info"}
            />
            <MetricCell
              icon={<Rocket className="h-3.5 w-3.5" />}
              label={t("detail.metricsPage.gpu")}
              value={gpuValue}
              detail={gpuDetail}
              muted={!latest?.gpu_available}
              progress={latest?.gpu_percent}
              progressColor="bg-chart-3"
            />
          </div>
        ) : (
          <div className="py-6 text-center text-style-caption text-color-muted-foreground">
            {activeStatuses.includes(job.status)
              ? t("detail.metricsPage.startingDescription")
              : t("detail.metricsPage.emptyDescription")}
          </div>
        )}
      </section>
    </div>
  );
}

function MetricCell({
  icon,
  label,
  value,
  detail,
  muted = false,
  warning = false,
  progress,
  progressColor,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
  muted?: boolean;
  warning?: boolean;
  progress?: number | null;
  progressColor?: string;
}) {
  return (
    <div
      className={`flex min-w-0 flex-col justify-between rounded-surface border bg-muted px-5 py-4 ${
        warning
          ? "border-warning-border ring-1 ring-warning-border"
          : "border-border"
      } ${muted ? "border-dashed opacity-50 grayscale" : ""}`}
    >
      <div>
        <div className="flex items-start justify-between">
          <p
            className={`flex items-center gap-1.5 text-style-caption font-bold uppercase ${
              warning ? "text-color-warning" : "text-color-muted-foreground"
            }`}
          >
            {icon}
            {label}
          </p>
          <p
            className={`truncate text-style-page-title font-bold ${
              warning
                ? "text-color-warning"
                : muted
                  ? "text-color-muted-foreground"
                  : "text-color-foreground"
            }`}
            title={value}
          >
            {value}
          </p>
        </div>
        {progress != null && !muted && (
          <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={`h-full transition-all duration-500 ${
                progressColor || "bg-border"
              }`}
              style={{
                width: `${Math.min(100, Math.max(0, progress))}%`,
              }}
            />
          </div>
        )}
      </div>
      <p
        className={`mt-3 truncate text-style-caption font-bold ${
          warning ? "text-color-warning" : "text-color-muted-foreground"
        }`}
        title={detail}
      >
        {detail}
      </p>
    </div>
  );
}
