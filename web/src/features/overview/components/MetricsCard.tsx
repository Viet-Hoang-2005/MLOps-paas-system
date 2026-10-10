import { formatNumber } from "@/shared/i18n/formatters";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { StepTitle } from "@/shared/components/StepTitle";
import { FileCode, Gauge, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  AttributeDropzoneCard,
  AttributeMissingVersionCard,
} from "./AttributeEmptyStateCards";

export interface MetricsCardProps {
  metrics?: Record<string, unknown> | null;
  summarySources?: Record<string, string>;
  filename?: string;
  projectId: string;
  versionId?: string;
  isPreview?: boolean;
  onRequestRemove?: () => void;
  onRefresh?: () => void;
  className?: string;
}

export function MetricsCard({
  metrics,
  summarySources,
  filename,
  projectId,
  versionId,
  isPreview = false,
  onRequestRemove,
  onRefresh,
  className = "",
}: MetricsCardProps) {
  const { t, i18n } = useTranslation("overview");
  const hasMetrics = Boolean(metrics && Object.keys(metrics).length > 0);

  if (!hasMetrics) {
    if (isPreview) {
      return (
        <AttributeDropzoneCard
          kind="metrics"
          accept=".json"
          title={t("workflow.metricsTitle")}
          hint={t("workflow.metricsHint")}
          icon={<Gauge className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          onSuccess={onRefresh ?? (() => {})}
          className={className}
        />
      );
    }
    return (
      <AttributeMissingVersionCard
        title={t("workflow.metricsTitle")}
        hint={t("workflow.missingAttributeInVersionHint")}
        icon={<Gauge className="h-5 w-5 text-color-primary" />}
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
          icon={<Gauge className="h-5 w-5 text-color-primary" />}
          title={t("workflow.metricsTitle")}
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
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
          {Object.entries(metrics!).map(([key, val]) => {
            const formattedVal =
              typeof val === "number"
                ? Number.isInteger(val)
                  ? val.toLocaleString()
                  : formatNumber(val, i18n.language, {
                      maximumFractionDigits: 6,
                    })
                : String(val);
            return (
              <div
                key={key}
                className="flex flex-col justify-between rounded-surface border border-border bg-muted p-4"
              >
                <span
                  className="truncate text-style-caption text-color-muted-foreground"
                  title={key}
                >
                  {key}
                </span>
                {summarySources?.[key] && (
                  <span className="text-style-caption text-color-muted-foreground">
                    {t(`workflow.${summarySources[key]}Source`)}
                  </span>
                )}
                <span
                  className="mt-2 truncate font-mono text-style-heading text-color-foreground"
                  title={String(val)}
                >
                  {formattedVal}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export default MetricsCard;

