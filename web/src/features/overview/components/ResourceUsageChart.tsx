import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useRuntimeMetrics } from "@/features/overview/hooks/useRuntimeMetrics";
import { Chart } from "@/shared/components/Chart";
import { Select } from "@/shared/components/Select";
import { StepTitle } from "@/shared/components/StepTitle";
import { formatDateTime, formatNumber } from "@/shared/i18n/formatters";

export function ResourceUsageChart({
  projectId,
  deploymentId,
}: {
  projectId: string;
  deploymentId: string;
}) {
  const { t, i18n } = useTranslation("overview");
  const [window, setWindow] = useState("1h");
  const metrics = useRuntimeMetrics(projectId, deploymentId, window);
  const realtime = metrics.data?.mode !== "history";

  const getMetricUnit = (key: "cpu" | "memory" | "requests") => {
    switch (key) {
      case "cpu":
        return "cores";
      case "memory":
        return "MiB";
      case "requests":
        return "req/s";
    }
  };

  return (
    <section className="space-y-6 rounded-surface border border-border bg-surface p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <StepTitle
          title={t("workflow.resourceUsage")}
          subtitle={t("workflow.realtimeHint")}
          className="mb-0"
        />
        {!realtime && (
          <div className="w-48">
            <Select
              value={window}
              onChange={setWindow}
              options={["15m", "1h", "24h"].map((value) => ({
                value,
                label: t(`workflow.range_${value}`),
              }))}
            />
          </div>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {(["cpu", "memory", "requests"] as const).map((key) => {
          const rawSamples: Array<[number, number | null]> = realtime
            ? (metrics.data?.points ?? []).map((point) => [
                point.timestamp,
                point[key],
              ])
            : (metrics.data?.series?.[key]?.[0]?.values ?? []).map(
                ([timestamp, value]) => [timestamp, Number(value)],
              );
          const data = rawSamples.map(([timestamp, value]) => ({
            timestamp,
            value,
          }));
          const current = metrics.isError ? null : rawSamples.at(-1)?.[1];
          const available = current !== null && current !== undefined;
          const unit = getMetricUnit(key);

          return (
            <div
              key={key}
              className="flex flex-col justify-between rounded-surface border border-border bg-muted/20 p-4"
            >
              <div>
                <h4 className="text-style-body-strong text-color-foreground">
                  {t(`workflow.metric_${key}`)}
                </h4>
                {available ? (
                  <p className="text-style-metric text-color-foreground">
                    {formatNumber(Number(current), i18n.language, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </p>
                ) : (
                  <p className="text-style-body text-color-muted-foreground">
                    {t(
                      metrics.isError || metrics.data?.status === "unavailable"
                        ? "workflow.unavailable"
                        : "workflow.noData",
                    )}
                  </p>
                )}
              </div>

              <div className="mt-4">
                <Chart
                  data={data}
                  valueFormatter={(val: number) =>
                    `${formatNumber(val, i18n.language, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })} ${unit}`
                  }
                  timeFormatter={(ts: number) =>
                    formatDateTime(ts * 1000, i18n.language, {
                      timeStyle: "medium",
                    })
                  }
                  emptyText={t(
                    metrics.isError || metrics.data?.status === "unavailable"
                      ? "workflow.unavailable"
                      : "workflow.noData",
                  )}
                />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
