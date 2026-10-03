import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { getRuntimeMetrics } from "@/features/projects/api/metricsApi";
import { projectOverviewKeys } from "@/features/projects/hooks/useProjectOverview";
import { Select } from "@/shared/components/Select";

export function RuntimeMetrics({ projectId }: { projectId: string }) {
  const { t } = useTranslation("projects");
  const [window, setWindow] = useState("1h");
  const metrics = useQuery({
    queryKey: projectOverviewKeys.metrics(projectId, window),
    queryFn: () => getRuntimeMetrics(projectId, window),
    refetchInterval: 15000,
  });
  return (
    <div className="space-y-4">
      <Select
        value={window}
        onChange={setWindow}
        options={["15m", "1h", "24h"].map((value) => ({
          value,
          label: t(`workflow.range_${value}`),
        }))}
      />
      <div className="grid gap-4 md:grid-cols-3">
        {(["cpu", "memory", "requests"] as const).map((key) => {
          const values =
            metrics.data?.series[key]?.[0]?.values.filter(([, value]) =>
              Number.isFinite(Number(value)),
            ) ?? [];
          const max = Math.max(
            ...values.map(([, value]) => Number(value)),
            0.001,
          );
          const start = values[0]?.[0] ?? 0;
          const duration = (values.at(-1)?.[0] ?? start) - start || 1;
          const points = values
            .map(
              ([timestamp, value]) =>
                `${((timestamp - start) / duration) * 300},${95 - (Number(value) / max) * 90}`,
            )
            .join(" ");
          return (
            <section
              key={key}
              className="rounded-surface border border-border p-4"
            >
              <h3 className="text-style-body-strong">
                {t(`workflow.metric_${key}`)}
              </h3>
              {values.length ? (
                <>
                  <p className="text-style-metric">
                    {Number(values.at(-1)![1]).toFixed(2)}
                  </p>
                  <svg
                    role="img"
                    aria-label={t(`workflow.metric_${key}`)}
                    viewBox="0 0 300 100"
                    className="w-full text-color-primary"
                  >
                    <polyline
                      points={points}
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    />
                  </svg>
                  <p className="text-style-caption text-color-muted-foreground">
                    {new Date(start * 1000).toLocaleTimeString()} –{" "}
                    {new Date(values.at(-1)![0] * 1000).toLocaleTimeString()}
                  </p>
                </>
              ) : (
                <p>
                  {t(
                    metrics.isError || metrics.data?.status === "unavailable"
                      ? "workflow.unavailable"
                      : "workflow.noData",
                  )}
                </p>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
