import type { ReactNode } from "react";
import { Activity, Cpu, HardDrive, RefreshCw, Rocket } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useTrainingJobDetailContext } from "@/features/training/trainingJobDetailContext";

const formatMetricPercent = (value: number) => `${Math.round(value)}%`;
const formatMegabytes = (megabytes: number) =>
  megabytes >= 1024
    ? `${(megabytes / 1024).toFixed(1)} GB`
    : `${Math.round(megabytes)} MB`;

export default function TrainingJobMetricsPage() {
  const { t } = useTranslation("training");
  const {
    job,
    activeStatuses,
    metrics,
    loadingMetrics,
    refreshingSection,
    refreshMetrics,
  } = useTrainingJobDetailContext();

  if (!metrics?.metrics_available && activeStatuses.includes(job.status)) {
    return (
      <div className="flex flex-col items-center justify-center rounded-surface border border-dashed border-border bg-muted px-4 py-16 text-center shadow-sm">
        <Activity className="mb-4 h-10 w-10 text-color-muted-foreground" />
        <p className="text-style-heading text-color-foreground">
          {t("detail.metricsPage.starting")}
        </p>
        <p className="mt-2 max-w-md text-style-body text-color-muted-foreground">
          {t("detail.metricsPage.startingDescription")}
        </p>
      </div>
    );
  }

  if (!metrics?.metrics_available) {
    return (
      <div className="flex flex-col items-center justify-center rounded-surface border border-border bg-surface px-4 py-16 text-center shadow-sm">
        <Activity className="mb-4 h-10 w-10 text-color-muted-foreground" />
        <p className="text-style-heading text-color-foreground">
          {t("detail.metricsPage.empty")}
        </p>
        <p className="mt-2 text-style-body text-color-muted-foreground">
          {t("detail.metricsPage.emptyDescription")}
        </p>
      </div>
    );
  }

  const latest = metrics.latest;
  const highCpu = latest?.cpu_percent != null && latest.cpu_percent > 85;
  const highRam =
    latest?.memory_percent != null && latest.memory_percent > 85;
  const memoryValue =
    latest?.memory_percent != null
      ? formatMetricPercent(latest.memory_percent)
      : latest?.memory_used_mb != null
        ? t("detail.metricsPage.memoryUsed", { memory: formatMegabytes(latest.memory_used_mb) })
        : "-";
  const memoryDetail =
    latest?.memory_used_mb != null && latest?.memory_limit_mb != null
      ? `${formatMegabytes(latest.memory_used_mb)} / ${formatMegabytes(
          latest.memory_limit_mb,
        )}`
      : latest?.memory_used_mb != null
        ? t("detail.metricsPage.memoryUsed", { memory: formatMegabytes(latest.memory_used_mb) })
        : metrics.message || t("detail.metricsPage.waitingRunner");
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
    <div className="animate-in space-y-4 fade-in duration-300">
      <div className="rounded-surface border border-border bg-surface p-6 shadow-sm">
        <div className="mb-6 flex items-center justify-between gap-3 border-b border-border pb-4">
          <p className="flex items-center gap-2 text-style-overline uppercase text-color-foreground">
            <Activity className="h-4 w-4 text-color-info" />
            {t("detail.metricsPage.title")}
          </p>
          <div className="flex items-center gap-3">
            <span className="text-style-caption-strong text-color-muted-foreground">
              {latest?.timestamp
                ? t("detail.metricsPage.sampled", {
                    time: new Date(latest.timestamp).toLocaleTimeString(),
                  })
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
                ? t("detail.metricsPage.cpuLimit", { count: latest.cpu_limit_cores })
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
      </div>
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
        warning ? "border-warning-border ring-1 ring-warning-border" : "border-border"
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
