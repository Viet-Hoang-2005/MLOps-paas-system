import type { ModelVersion } from "@/features/projects/types";
import { useTranslation } from "react-i18next";
import { formatNumber } from "@/shared/i18n/formatters";

export function SnapshotMetadata({ version }: { version: ModelVersion }) {
  const { t, i18n } = useTranslation("evolution");
  const sections = [
    { title: `${t("snapshot.metrics")} · ${t("snapshot.registeredSource")}`, value: version.metrics_summary },
    { title: `${t("snapshot.params")} · ${t("snapshot.registeredSource")}`, value: version.params_summary },
    { title: `${t("snapshot.insights")} · ${t("snapshot.registeredSource")}`, value: version.insights_summary },
    ...Object.entries(version.supplemental_summaries ?? {}).map(([kind, item]) => ({
      title: `${kind} · ${t("snapshot.supplementalSource")}`,
      value: item.value as Record<string, unknown>,
    })),
  ].filter((section) => Object.keys(section.value ?? {}).length > 0);
  return (
    <div className="space-y-5">
      {sections.map((section) => (
        <section
          key={section.title}
          className="rounded-surface border border-border bg-surface p-4"
        >
          <h3 className="text-style-heading">{section.title}</h3>
          <pre className="mt-3 overflow-auto text-style-code-sm">
            {JSON.stringify(section.value, null, 2)}
          </pre>
        </section>
      ))}
      {version.metrics_summary &&
        Object.entries(version.metrics_summary).filter(
          ([, value]) => typeof value === "number",
        ).length > 0 && (
          <div className="grid gap-3 sm:grid-cols-3">
            {Object.entries(version.metrics_summary)
              .filter(([, value]) => typeof value === "number")
              .map(([name, value]) => (
                <div
                  key={name}
                  className="rounded-surface border border-border bg-muted p-4"
                >
                  <p className="text-style-caption">{name}</p>
                  <p className="text-style-heading">
                    {formatNumber(Number(value), i18n.language, {
                      maximumFractionDigits: 6,
                    })}
                  </p>
                </div>
              ))}
          </div>
        )}
      {version.insights_summary?.items?.length ? (
        <section aria-label={t("snapshot.insights")} className="space-y-3">
          {version.insights_summary.items.slice(0, 20).map((item, index) => {
            const max = Math.max(
              ...version.insights_summary.items!.map((value) =>
                Math.abs(value.value),
              ),
              1e-10,
            );
            return (
              <div key={`${item.name}-${index}`} className="space-y-1">
                <p className="text-style-caption">
                  {item.name}:{" "}
                  {formatNumber(item.value, i18n.language, {
                    maximumFractionDigits: 6,
                  })}
                </p>
                <div className="h-3 rounded-compact bg-muted">
                  <div
                    className="h-3 rounded-compact bg-chart-1"
                    style={{ width: `${(Math.abs(item.value) / max) * 100}%` }}
                  />
                </div>
              </div>
            );
          })}
        </section>
      ) : null}
    </div>
  );
}
