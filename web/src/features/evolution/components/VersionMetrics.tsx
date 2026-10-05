import type { ModelVersion } from "@/features/projects/types";
import { metricSeries } from "@/features/evolution/evolutionState";
import { Chart } from "@/shared/components/Chart";
import { VersionRecords } from "./VersionRecords";
import { formatNumber, formatDateTime } from "@/shared/i18n/formatters";
import { useTranslation } from "react-i18next";

export function VersionMetrics({ version }: { version: ModelVersion }) {
  const { t, i18n } = useTranslation("evolution");
  const summary = Object.entries(version.metrics_summary);
  const series = metricSeries(version.metrics);
  const number = (value: number) =>
    formatNumber(value, i18n.language, { maximumFractionDigits: 6 });
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {summary
          .filter(
            ([, value]) => typeof value === "number" && Number.isFinite(value),
          )
          .map(([name, value]) => (
            <div
              key={name}
              className="rounded-surface border border-border bg-muted p-4"
            >
              <p className="text-style-caption text-color-muted-foreground">
                {name}
              </p>
              <p className="mt-2 text-style-metric">{number(Number(value))}</p>
            </div>
          ))}
      </div>
      <VersionRecords
        rows={summary.map(([name, value]) => ({ name, value }))}
        columns={[
          { key: "name", title: t("workspace.name") },
          { key: "value", title: t("workspace.value") },
        ]}
        empty={t("workspace.noMetrics")}
      />
      <section className="space-y-4">
        <h3 className="text-style-heading">{t("workspace.metricHistory")}</h3>
        {!series.length && (
          <p className="text-color-muted-foreground">
            {t("workspace.noMetricHistory")}
          </p>
        )}
        <div className="grid gap-4 lg:grid-cols-2">
          {series.map(({ name, points }) => {
            const steps = [
              ...new Map(
                points.map((point) => [point.step!, point.value]),
              ).entries(),
            ];
            return (
              <section
                key={name}
                className="space-y-3 rounded-surface border border-border p-4"
              >
                <h4 className="text-style-body-strong">{name}</h4>
                <Chart
                  allowNegative
                  data={steps.map(([step, value]) => ({
                    timestamp: step,
                    value,
                  }))}
                  timeFormatter={(step) =>
                    `${t("workspace.step")} ${number(step)}`
                  }
                  valueFormatter={number}
                  emptyText={t("workspace.insufficientPoints")}
                />
              </section>
            );
          })}
        </div>
        {version.metrics.length > 0 && (
          <VersionRecords
            rows={version.metrics.map((metric) => ({
              name: metric.name,
              value: metric.value,
              step: metric.step,
              timestamp: metric.timestamp
                ? formatDateTime(metric.timestamp, i18n.language)
                : null,
            }))}
            columns={[
              { key: "name", title: t("workspace.name") },
              { key: "value", title: t("workspace.value") },
              { key: "step", title: t("workspace.step") },
              { key: "timestamp", title: t("workspace.timestamp") },
            ]}
            empty={t("workspace.noMetricHistory")}
          />
        )}
      </section>
    </div>
  );
}
