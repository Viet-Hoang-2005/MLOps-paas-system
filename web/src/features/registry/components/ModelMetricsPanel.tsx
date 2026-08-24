/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState, useCallback, useMemo } from "react";
import { getRegistryMetrics } from "@/features/registry/api/registryApi";
import type { RegistryMetric } from "@/features/registry/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/components/toastStore";
import { BarChart2 } from "lucide-react";
import { useTranslation } from "react-i18next";

interface Props {
  familyId: string;
  versionId: string;
}

export function ModelMetricsPanel({ familyId, versionId }: Props) {
  const [metrics, setMetrics] = useState<Record<string, RegistryMetric[]>>({});
  const [loading, setLoading] = useState(true);
  const { t } = useTranslation("registry");

  const fetchMetrics = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getRegistryMetrics(familyId, versionId);
      setMetrics(data);
    } catch (error) {
      toast.error(getApiErrorMessage(error, t("metricsPanel.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [familyId, versionId, t]);

  useEffect(() => {
    void fetchMetrics();
  }, [fetchMetrics]);

  // Compute stats for rendering
  const metricEntries = useMemo(() => {
    return Object.entries(metrics)
      .map(([name, dataPoints]) => {
        if (dataPoints.length === 0) return null;

        const sorted = [...dataPoints].sort((a, b) => a.step - b.step);
        const latest = sorted[sorted.length - 1];
        const values = sorted.map((d) => d.value);
        const min = Math.min(...values);
        const max = Math.max(...values);

        // Calculate height percentages for the mini chart
        // We add a tiny buffer so lines don't hit the absolute top/bottom unless it's exactly 0/100
        const range = max - min || 1;
        const chartPoints = sorted.map((d) => ({
          ...d,
          heightPct: Math.max(5, ((d.value - min) / range) * 100),
        }));

        return {
          name,
          latest,
          min,
          max,
          chartPoints,
        };
      })
      .filter(Boolean);
  }, [metrics]);

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="h-8 w-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (metricEntries.length === 0) {
    return (
      <div className="text-center py-12 flex flex-col items-center border border-dashed border-border rounded-surface bg-muted/50 px-6 max-w-3xl mx-auto">
        <div className="rounded-full bg-surface border border-border p-4 mb-4 shadow-sm">
          <BarChart2 className="h-8 w-8 text-color-muted-foreground" />
        </div>
        <h3 className="text-style-heading font-bold text-color-foreground mb-2">
          {t("metricsPanel.emptyTitle")}
        </h3>
        <p className="text-style-body text-color-muted-foreground max-w-lg mb-6">
          {t("metricsPanel.exampleDescription")}
        </p>

        <div className="mb-4 w-full overflow-hidden rounded-surface border border-terminal-border bg-terminal text-left shadow-sm">
          <div className="flex items-center justify-between border-b border-terminal-border bg-terminal-header px-3 py-1.5">
            <div className="flex items-center gap-3">
              <div className="flex gap-1.5">
                <div className="h-2.5 w-2.5 rounded-full bg-terminal-muted"></div>
                <div className="h-2.5 w-2.5 rounded-full bg-terminal-muted"></div>
                <div className="h-2.5 w-2.5 rounded-full bg-terminal-muted"></div>
              </div>
              <span className="font-mono text-style-code-sm text-color-muted-foreground">
                train.py - metric output contract
              </span>
            </div>
            <button
              className="text-style-caption text-color-terminal-muted transition-colors hover:text-color-terminal-foreground"
              onClick={() => {
                navigator.clipboard.writeText(
                  'import json\n\n# METRIC_JSON stdout works without extra dependencies.\nprint("METRIC_JSON:", json.dumps({\n    "step": 1,\n    "accuracy": 0.95,\n    "loss": 0.12,\n    "f1": 0.93\n}))',
                );
                toast.success(t("metricsPanel.copied"));
              }}
            >
              {t("actions.copy", { ns: "common" })}
            </button>
          </div>
          <div className="p-4">
            <pre className="overflow-x-auto font-mono text-style-code-sm text-color-terminal-success">
              <code>{`import json

# METRIC_JSON stdout works without extra dependencies.
print("METRIC_JSON:", json.dumps({
    "step": 1,
    "accuracy": 0.95,
    "loss": 0.12,
    "f1": 0.93
}))`}</code>
            </pre>
          </div>
        </div>

        <p className="text-style-caption-strong text-color-muted-foreground">
          {t("metricsPanel.syncHint")}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Metric Cards grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {metricEntries.map((m) => {
          if (!m) return null;
          return (
            <div
              key={`card-${m.name}`}
              className="bg-muted border border-border rounded-surface p-4"
            >
              <p
                className="text-style-caption-strong text-color-muted-foreground uppercase mb-1 truncate"
                title={m.name}
              >
                {m.name.replace(/_/g, " ")}
              </p>
              <div className="flex items-end gap-2">
                <span className="text-style-page-title font-bold text-color-foreground">
                  {Number.isInteger(m.latest.value)
                    ? m.latest.value
                    : m.latest.value.toFixed(4)}
                </span>
                <span className="text-style-caption text-color-muted-foreground mb-1">
                  {t("metricsPanel.step")} {m.latest.step}
                </span>
              </div>
              <p className="text-style-caption text-color-muted-foreground uppercase mt-2">
                {t("metricsPanel.source", { source: m.latest.source })}
              </p>
            </div>
          );
        })}
      </div>

      {/* Lightweight SVG Charts & Trend Table */}
      <div className="grid lg:grid-cols-2 gap-6">
        {metricEntries.map((m) => {
          if (!m) return null;

          // Generate SVG polyline points
          const width = 300;
          const height = 100;
          const points = m.chartPoints
            .map((point, idx) => {
              const x = (idx / Math.max(1, m.chartPoints.length - 1)) * width;
              const y = height - (point.heightPct / 100) * height;
              return `${x},${y}`;
            })
            .join(" ");

          const last5 = [...m.chartPoints].reverse().slice(0, 5);

          return (
            <div
              key={`chart-${m.name}`}
              className="border border-border bg-surface shadow-sm rounded-surface p-5"
            >
              <div className="flex justify-between items-center mb-4">
                <h4 className="text-style-body-strong text-color-foreground capitalize">
                  {t("metricsPanel.progression", { name: m.name.replace(/_/g, " ") })}
                </h4>
                <span className="text-style-caption text-color-muted-foreground font-mono bg-muted px-2 py-1 rounded-compact">
                  {t("metricsPanel.range", {
                    min: m.min.toFixed(2),
                    max: m.max.toFixed(2),
                  })}
                </span>
              </div>

              <div className="w-full bg-muted rounded-surface p-4 border border-border flex flex-col gap-2">
                <svg
                  viewBox={`0 0 ${width} ${height}`}
                  className="h-32 w-full fill-none stroke-chart-1 overflow-visible"
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient
                      id={`grad-${m.name}`}
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop offset="0%" stopColor="var(--chart-1)" stopOpacity="0.2" />
                      <stop offset="100%" stopColor="var(--chart-1)" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  {/* Fill Area */}
                  <polygon
                    points={`0,${height} ${points} ${width},${height}`}
                    fill={`url(#grad-${m.name})`}
                    className="stroke-none"
                  />
                  {/* Line */}
                  <polyline
                    points={points}
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  {/* Points */}
                  {m.chartPoints.map((point, idx) => {
                    const x =
                      (idx / Math.max(1, m.chartPoints.length - 1)) * width;
                    const y = height - (point.heightPct / 100) * height;
                    return (
                      <circle
                        key={idx}
                        cx={x}
                        cy={y}
                        r="3"
                        className="fill-surface stroke-chart-1 stroke-2"
                      />
                    );
                  })}
                </svg>
                <div className="flex justify-between text-style-caption text-color-muted-foreground font-mono px-1">
                  <span>{t("metricsPanel.step")} {m.chartPoints[0].step}</span>
                  <span>{t("metricsPanel.step")} {m.latest.step}</span>
                </div>
              </div>

              {/* Trend Table */}
              <div className="mt-6">
                <h5 className="text-style-caption-strong text-color-muted-foreground uppercase mb-2">
                  {t("metricsPanel.recentTrend")}
                </h5>
                <div className="border border-border rounded-surface overflow-hidden">
                  <table className="w-full text-style-body text-left">
                    <thead className="bg-muted text-color-muted-foreground text-style-caption uppercase font-semibold">
                      <tr>
                        <th className="px-3 py-2">{t("metricsPanel.step")}</th>
                        <th className="px-3 py-2 text-right">{t("metricsPanel.value")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {last5.map((point) => (
                        <tr key={point.step} className="bg-surface">
                          <td className="px-3 py-2 font-mono text-color-muted-foreground">
                            {point.step}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-color-foreground">
                            {Number.isInteger(point.value)
                              ? point.value
                              : point.value.toFixed(4)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
