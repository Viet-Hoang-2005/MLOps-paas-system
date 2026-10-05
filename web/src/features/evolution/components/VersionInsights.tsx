import type { ModelVersion } from "@/features/projects/types";
import { VersionRecords } from "./VersionRecords";
import { formatNumber } from "@/shared/i18n/formatters";
import { useTranslation } from "react-i18next";

export function VersionInsights({ version }: { version: ModelVersion }) {
  const { t, i18n } = useTranslation("evolution");
  const insights = version.insights_summary;
  const items = [...(insights.items ?? [])]
    .filter((item) => Number.isFinite(item.value))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  if (!Object.keys(insights).length)
    return (
      <p className="text-color-muted-foreground">{t("workspace.noInsights")}</p>
    );
  const top = items.slice(0, 20);
  const max = Math.max(...top.map((item) => Math.abs(item.value)), 1e-10);
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          [t("workspace.insightKind"), insights.kind],
          [t("workspace.source"), insights.source],
          [
            t("workspace.features"),
            formatNumber(insights.feature_count ?? items.length, i18n.language),
          ],
        ].map(([label, value]) => (
          <div
            key={label}
            className="rounded-surface border border-border bg-muted p-4"
          >
            <p className="text-style-caption text-color-muted-foreground">
              {label}
            </p>
            <p className="mt-2 text-style-heading">
              {value || t("workspace.missing")}
            </p>
          </div>
        ))}
      </div>
      {top.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-style-heading">
            {t("workspace.topFeatures", { count: top.length })}
          </h3>
          {top.map((item, index) => (
            <div
              key={`${item.name}:${item.class_name}:${index}`}
              className="space-y-1"
            >
              <div className="flex justify-between gap-4 text-style-caption">
                <span>
                  {item.name}
                  {item.class_name ? ` · ${item.class_name}` : ""}
                </span>
                <span>
                  {formatNumber(item.value, i18n.language, {
                    maximumFractionDigits: 6,
                  })}
                </span>
              </div>
              <div aria-hidden className="h-3 rounded-compact bg-muted">
                <div
                  className={`h-3 rounded-compact ${item.value < 0 ? "bg-chart-2" : "bg-chart-1"}`}
                  style={{ width: `${(Math.abs(item.value) / max) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </section>
      )}
      <VersionRecords
        rows={items.map((item, index) => ({
          rank: item.rank ?? index + 1,
          name: item.name,
          class: item.class_name,
          value: item.value,
        }))}
        columns={[
          { key: "rank", title: t("workspace.rank") },
          { key: "name", title: t("workspace.feature") },
          { key: "class", title: t("workspace.class") },
          { key: "value", title: t("workspace.value") },
        ]}
        empty={t("workspace.noInsights")}
      />
    </div>
  );
}
