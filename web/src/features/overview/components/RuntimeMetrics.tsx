import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useRuntimeMetrics } from "@/features/overview/hooks/useRuntimeMetrics";
import { Select } from "@/shared/components/Select";

export function RuntimeMetrics({
  projectId,
  deploymentId,
}: {
  projectId: string;
  deploymentId: string;
}) {
  const { t } = useTranslation("overview");
  const [window, setWindow] = useState("1h");
  const metrics = useRuntimeMetrics(projectId, deploymentId, window);
  const realtime = metrics.data?.mode !== "history";
  return (
    <div className="space-y-4">
      {realtime ? (
        <p className="text-style-caption text-color-muted-foreground">
          {t("workflow.realtimeHint")}
        </p>
      ) : (
        <Select
          value={window}
          onChange={setWindow}
          options={["15m", "1h", "24h"].map((value) => ({
            value,
            label: t(`workflow.range_${value}`),
          }))}
        />
      )}
      <div className="grid gap-4 md:grid-cols-3">
        {(["cpu", "memory", "requests"] as const).map((key) => {
          const samples: Array<[number, number | null]> = realtime
            ? (metrics.data?.points ?? []).map((point) => [
                point.timestamp,
                point[key],
              ])
            : (metrics.data?.series?.[key]?.[0]?.values ?? []).map(
                ([timestamp, value]) => [timestamp, Number(value)],
              );
          const values = samples.filter(
            ([, value]) => value !== null && Number.isFinite(value),
          );
          const current = metrics.isError ? null : samples.at(-1)?.[1];
          const available = current !== null && current !== undefined;
          /* Each gap starts a new path: don't imply observations during outages. */
          const validValues = values.filter(([, value]) =>
            Number.isFinite(Number(value)),
          );
          const max = Math.max(
            ...validValues.map(([, value]) => Number(value)),
            0.001,
          );
          const start = values[0]?.[0] ?? 0;
          const duration = (values.at(-1)?.[0] ?? start) - start || 1;
          let connected = false;
          const path = samples
            .map(([timestamp, value]) => {
              if (value === null || !Number.isFinite(value)) {
                connected = false;
                return "";
              }
              const point = `${((timestamp - start) / duration) * 300},${95 - (value / max) * 90}`;
              const segment = `${connected ? "L" : "M"}${point}`;
              connected = true;
              return segment;
            })
            .join(" ");
          return (
            <section
              key={key}
              className="rounded-surface border border-border p-4"
            >
              <h3 className="text-style-body-strong">
                {t(`workflow.metric_${key}`)}
              </h3>
              {available ? (
                <>
                  <p className="text-style-metric">
                    {Number(current).toFixed(2)}
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
              {values.length > 0 && (
                <>
                  <svg
                    role="img"
                    aria-label={t(`workflow.metric_${key}`)}
                    viewBox="0 0 300 100"
                    className="w-full text-color-primary"
                  >
                    <path
                      d={path}
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
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
