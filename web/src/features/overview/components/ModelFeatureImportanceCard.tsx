import type { ModelInsightItem } from "@/shared/api/catalogApi";
import { formatNumber } from "@/shared/i18n/formatters";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { StepTitle } from "@/shared/components/StepTitle";
import { BarChart3, FileCode, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AttributeDropzoneCard,
  AttributeMissingVersionCard,
} from "./AttributeEmptyStateCards";

export interface ModelFeatureImportanceCardProps {
  featureImportance?: { items?: ModelInsightItem[] } | null;
  insights?: { kind?: string; items?: ModelInsightItem[] } | null;
  summarySource?: string | null;
  filename?: string;
  projectId: string;
  versionId?: string;
  isPreview?: boolean;
  onRequestRemove?: () => void;
  onRefresh?: () => void;
  className?: string;
}

export function ModelFeatureImportanceCard({
  featureImportance,
  insights,
  summarySource,
  filename,
  projectId,
  versionId,
  isPreview = false,
  onRequestRemove,
  onRefresh,
  className = "",
}: ModelFeatureImportanceCardProps) {
  const { t, i18n } = useTranslation("overview");
  const [showAllInsights, setShowAllInsights] = useState(false);

  const insightItems: ModelInsightItem[] = useMemo(() => {
    const raw = featureImportance?.items || insights?.items;
    if (!raw) return [];
    return [...raw]
      .filter((item) => Number.isFinite(item.value))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  }, [featureImportance, insights]);

  const maxInsightValue = useMemo(() => {
    if (insightItems.length === 0) return 1;
    return Math.max(
      ...insightItems.map((item) => Math.abs(item.value)),
      1e-10,
    );
  }, [insightItems]);

  const displayedInsights = showAllInsights
    ? insightItems
    : insightItems.slice(0, 10);

  const hasFeatureImportance = Boolean(insightItems.length > 0);

  if (!hasFeatureImportance) {
    if (isPreview) {
      return (
        <AttributeDropzoneCard
          kind="feature_importance"
          accept=".json"
          title={t("workflow.featureImportanceTitle")}
          hint={t("workflow.featureImportanceHint")}
          icon={<BarChart3 className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          onSuccess={onRefresh ?? (() => {})}
          className={className}
        />
      );
    }
    return (
      <AttributeMissingVersionCard
        title={t("workflow.featureImportanceTitle")}
        hint={t("workflow.missingAttributeInVersionHint")}
        icon={<BarChart3 className="h-5 w-5 text-color-primary" />}
        projectId={projectId}
        versionId={versionId}
        className={className}
      />
    );
  }

  return (
    <section
      className={`rounded-surface border border-border bg-surface p-6 flex flex-col justify-between ${className}`}
    >
      <div>
        <StepTitle
          icon={<BarChart3 className="h-5 w-5 text-color-primary" />}
          title={
            <span className="flex items-center gap-2">
              <span>{t("workflow.featureImportanceTitle")}</span>
              {summarySource && (
                <span className="text-style-caption text-color-muted-foreground">
                  {t(`workflow.${summarySource}Source`)}
                </span>
              )}
              <span className="text-style-caption text-color-muted-foreground">
                ({t("workflow.totalFeatures")}: {insightItems.length})
              </span>
            </span>
          }
          className="mb-6"
          action={
            <div className="flex items-center gap-2 flex-wrap">
              {filename && (
                <Badge
                  variant="neutral"
                  className="font-mono text-style-caption text-color-muted-foreground"
                >
                  <FileCode className="h-3.5 w-3.5" />
                  <span>{filename}</span>
                </Badge>
              )}
              {insightItems.length > 10 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowAllInsights(!showAllInsights)}
                >
                  {showAllInsights
                    ? t("workflow.showTopFeatures", { count: 10 })
                    : t("workflow.showAllFeatures", {
                        count: insightItems.length,
                      })}
                </Button>
              )}
              {isPreview && onRequestRemove && (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Trash2 className="h-3.5 w-3.5 text-color-danger" />}
                  onClick={onRequestRemove}
                >
                  {t("workflow.removeAttribute")}
                </Button>
              )}
            </div>
          }
        />

        <div className="space-y-3">
          {displayedInsights.map((item, index) => {
            const absVal = Math.abs(item.value);
            const percentage = (absVal / maxInsightValue) * 100;
            const formattedValue = formatNumber(item.value, i18n.language, {
              maximumFractionDigits: 6,
            });

            return (
              <div
                key={`${item.name}:${item.class_name ?? ""}:${index}`}
                className="space-y-1.5"
              >
                <div className="flex items-center justify-between gap-4 text-style-caption">
                  <span className="font-mono text-color-foreground">
                    {item.name}
                    {item.class_name ? ` · ${item.class_name}` : ""}
                  </span>
                  <span className="font-mono text-color-muted-foreground">
                    {formattedValue}
                  </span>
                </div>
                <div
                  aria-hidden
                  className="h-2.5 w-full overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className={`h-full rounded-full transition-all duration-300 ease-out ${
                      item.value < 0 ? "bg-chart-2" : "bg-chart-1"
                    }`}
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export default ModelFeatureImportanceCard;

