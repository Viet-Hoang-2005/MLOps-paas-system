import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { StepTitle } from "@/shared/components/StepTitle";
import { FileCode, SlidersHorizontal, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  AttributeDropzoneCard,
  AttributeMissingVersionCard,
} from "./AttributeEmptyStateCards";

export interface ModelHyperparametersCardProps {
  params?: Record<string, unknown> | null;
  summarySources?: Record<string, string>;
  filename?: string;
  projectId: string;
  versionId?: string;
  isPreview?: boolean;
  onRequestRemove?: () => void;
  onRefresh?: () => void;
  className?: string;
}

export function ModelHyperparametersCard({
  params,
  summarySources,
  filename,
  projectId,
  versionId,
  isPreview = false,
  onRequestRemove,
  onRefresh,
  className = "",
}: ModelHyperparametersCardProps) {
  const { t } = useTranslation("overview");
  const hasParams = Boolean(params && Object.keys(params).length > 0);

  if (!hasParams) {
    if (isPreview) {
      return (
        <AttributeDropzoneCard
          kind="params"
          accept=".json"
          title={t("workflow.paramsTitle")}
          hint={t("workflow.paramsHint")}
          icon={<SlidersHorizontal className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          onSuccess={onRefresh ?? (() => {})}
          className={className}
        />
      );
    }
    return (
      <AttributeMissingVersionCard
        title={t("workflow.paramsTitle")}
        hint={t("workflow.missingAttributeInVersionHint")}
        icon={<SlidersHorizontal className="h-5 w-5 text-color-primary" />}
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
          icon={<SlidersHorizontal className="h-5 w-5 text-color-primary" />}
          title={t("workflow.paramsTitle")}
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
                    size="sm"
                    variant="secondary"
                    icon={<Trash2 className="h-3.5 w-3.5 text-color-danger" />}
                    onClick={onRequestRemove}
                  >
                    {t("workflow.removeAttribute")}
                  </Button>
                )}
              </div>
            ) : undefined
          }
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Object.entries(params!).map(([key, val]) => (
            <div
              key={key}
              className="rounded-surface border border-border bg-muted p-3"
            >
              <div
                className="truncate text-style-caption text-color-muted-foreground"
                title={key}
              >
                {key}
              </div>
              {summarySources?.[key] && (
                <div className="text-style-caption text-color-muted-foreground">
                  {t(`workflow.${summarySources[key]}Source`)}
                </div>
              )}
              <div
                className="mt-1 truncate font-mono text-style-body text-color-foreground"
                title={String(val)}
              >
                {typeof val === "object" ? JSON.stringify(val) : String(val)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default ModelHyperparametersCard;

