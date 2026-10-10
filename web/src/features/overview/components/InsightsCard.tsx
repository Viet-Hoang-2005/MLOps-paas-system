import type { ModelInsightsSummary } from "@/shared/api/catalogApi";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { StepTitle } from "@/shared/components/StepTitle";
import { FileCode, Layers, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  AttributeDropzoneCard,
  AttributeMissingVersionCard,
} from "./AttributeEmptyStateCards";

export interface InsightsCardProps {
  insights?: ModelInsightsSummary | Record<string, unknown> | null;
  summarySource?: string | null;
  filename?: string;
  projectId: string;
  versionId?: string;
  isPreview?: boolean;
  onRequestRemove?: () => void;
  onRefresh?: () => void;
  className?: string;
}

export function InsightsCard({
  insights,
  summarySource,
  filename,
  projectId,
  versionId,
  isPreview = false,
  onRequestRemove,
  onRefresh,
  className = "",
}: InsightsCardProps) {
  const { t } = useTranslation("overview");

  const hasInsights = Boolean(
    insights &&
      typeof insights === "object" &&
      Object.keys(insights).length > 0 &&
      !(insights.kind === "feature_importance" && Object.keys(insights).length <= 2),
  );

  if (!hasInsights) {
    if (isPreview) {
      return (
        <AttributeDropzoneCard
          kind="model_insights"
          accept=".json"
          title={t("workflow.insightsTitle")}
          hint={t("workflow.insightsHint")}
          icon={<Layers className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          onSuccess={onRefresh ?? (() => {})}
          className={className}
        />
      );
    }
    return (
      <AttributeMissingVersionCard
        title={t("workflow.insightsTitle")}
        hint={t("workflow.missingAttributeInVersionHint")}
        icon={<Layers className="h-5 w-5 text-color-primary" />}
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
          icon={<Layers className="h-5 w-5 text-color-primary" />}
          title={
            <span className="flex items-center gap-2">
              {t("workflow.insightsTitle")}
              {summarySource && (
                <span className="text-style-caption text-color-muted-foreground">
                  {t(`workflow.${summarySource}Source`)}
                </span>
              )}
            </span>
          }
          className="mb-6"
          action={
            filename || (isPreview && onRequestRemove) ? (
              <div className="flex items-center gap-2">
                {filename && (
                  <Badge
                    variant="neutral"
                    className="font-mono text-style-caption text-color-muted-foreground"
                  >
                    <FileCode className="h-3.5 w-3.5" />
                    <span>{filename}</span>
                  </Badge>
                )}
                {isPreview && onRequestRemove && (
                  <Button
                    size="icon"
                    border={false}
                    variant="secondary"
                    icon={<Trash2 className="h-4 w-4" />}
                    onClick={onRequestRemove}
                    title={t("workflow.removeAttribute")}
                    aria-label={t("workflow.removeAttribute")}
                  >
                  </Button>
                )}
              </div>
            ) : undefined
          }
        />
        <pre className="max-h-80 overflow-auto rounded-surface border border-border bg-muted p-4 font-mono text-style-caption text-color-foreground">
          {JSON.stringify(insights, null, 2)}
        </pre>
      </div>
    </section>
  );
}

export default InsightsCard;

