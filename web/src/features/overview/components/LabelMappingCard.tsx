import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { StepTitle } from "@/shared/components/StepTitle";
import { FileCode, ListTree, Trash2 } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  AttributeDropzoneCard,
  AttributeMissingVersionCard,
} from "./AttributeEmptyStateCards";

export interface LabelMappingCardProps {
  labelMapping?: { filename?: string; mapping?: unknown } | null;
  filename?: string;
  projectId: string;
  versionId?: string;
  isPreview?: boolean;
  onRequestRemove?: () => void;
  onRefresh?: () => void;
  className?: string;
}

export function LabelMappingCard({
  labelMapping,
  filename,
  projectId,
  versionId,
  isPreview = false,
  onRequestRemove,
  onRefresh,
  className = "",
}: LabelMappingCardProps) {
  const { t } = useTranslation("overview");

  const effectiveFilename = filename || labelMapping?.filename;

  const labelMappingEntries = useMemo<[string, string][]>(() => {
    if (!labelMapping?.mapping) return [];
    if (Array.isArray(labelMapping.mapping)) {
      return labelMapping.mapping.map((val, idx) => [
        String(idx),
        String(val),
      ]);
    }
    if (
      typeof labelMapping.mapping === "object" &&
      labelMapping.mapping !== null
    ) {
      return Object.entries(labelMapping.mapping).map(([k, v]) => [
        k,
        typeof v === "object" ? JSON.stringify(v) : String(v),
      ]);
    }
    return [];
  }, [labelMapping]);

  const hasLabelMapping = Boolean(
    labelMapping?.mapping && labelMappingEntries.length > 0,
  );

  if (!hasLabelMapping) {
    if (isPreview) {
      return (
        <AttributeDropzoneCard
          kind="label_mapping"
          accept=".json"
          title={t("workflow.labelMappingTitle")}
          hint={t("workflow.labelMappingHint")}
          icon={<ListTree className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          onSuccess={onRefresh ?? (() => {})}
          className={className}
        />
      );
    }
    return (
      <AttributeMissingVersionCard
        title={t("workflow.labelMappingTitle")}
        hint={t("workflow.missingAttributeInVersionHint")}
        icon={<ListTree className="h-5 w-5 text-color-primary" />}
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
          icon={<ListTree className="h-5 w-5 text-color-primary" />}
          title={t("workflow.labelMappingTitle")}
          className="mb-6"
          action={
            effectiveFilename || (isPreview && onRequestRemove) ? (
              <div className="flex items-center gap-2">
                {effectiveFilename && (
                  <Badge
                    variant="neutral"
                    className="font-mono text-style-caption text-color-muted-foreground"
                  >
                    <FileCode className="h-3.5 w-3.5" />
                    <span>{effectiveFilename}</span>
                  </Badge>
                )}
                {isPreview && onRequestRemove && (
                  <Button
                    size="icon"
                    border={false}
                    variant="secondary"
                    icon={<Trash2 className="h-4 w-4" />}
                    onClick={onRequestRemove}
                    title={t("workflow.removeLabelMapping")}
                    aria-label={t("workflow.removeLabelMapping")}
                  >
                  </Button>
                )}
              </div>
            ) : undefined
          }
        />
        <div className="space-y-3">
          {labelMappingEntries.map(([k, v]) => (
            <div
              key={k}
              className="flex items-center gap-2 py-1"
            >
              {/* Khối giá trị số mô hình trả về (Model Output) */}
              <div
                className="flex h-9 min-w-10 shrink-0 items-center justify-center rounded-surface border border-border bg-muted px-3 font-mono text-style-body font-semibold text-color-foreground shadow-xs"
                title={k}
              >
                {k}
              </div>

              {/* Đường thẳng nối với mũi tên trỏ sang phải */}
              <div className="relative flex flex-1 items-center min-w-6">
                <div className="h-px w-full bg-border" />
              </div>

              {/* Khối giá trị nhãn ánh xạ (Mapped Label) */}
              <div
                className="flex h-9 max-w-[65%] shrink-0 items-center rounded-surface border border-border bg-muted/50 px-4 font-mono text-style-body font-semibold text-color-foreground shadow-xs truncate"
                title={v}
              >
                <span className="truncate">{v}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default LabelMappingCard;
