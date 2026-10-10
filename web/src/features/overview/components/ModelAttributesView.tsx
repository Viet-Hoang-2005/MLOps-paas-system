import type { ModelAttributesResponse } from "@/shared/api/catalogApi";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { toast } from "@/shared/types/toastStore";
import { getApiErrorMessage } from "@/shared/api/errors";
import {
  removePreviewAsset,
  type PreviewSingleAssetKind,
} from "@/features/projects/api/previewApi";
import { overviewQueryKeys } from "@/features/overview/queryKeys";
import { previewKeys } from "@/features/projects/hooks/usePreview";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MetricsCard } from "./MetricsCard";
import { HyperparametersCard } from "./HyperparametersCard";
import { FeatureImportanceCard } from "./FeatureImportanceCard";
import { LabelMappingCard } from "./LabelMappingCard";
import { InputSchemaCard } from "./InputSchemaCard";
import { InsightsCard } from "./InsightsCard";

export interface ModelAttributesViewProps {
  attributes?: ModelAttributesResponse | null;
  projectId: string;
  versionId?: string;
  isPreview?: boolean;
}

export function ModelAttributesView({
  attributes,
  projectId,
  versionId,
  isPreview = false,
}: ModelAttributesViewProps) {
  const { t } = useTranslation("overview");
  const client = useQueryClient();
  const [removingAttribute, setRemovingAttribute] = useState<{
    kind: PreviewSingleAssetKind;
    title: string;
  } | null>(null);

  const metrics = attributes?.metrics ?? null;
  const params = attributes?.params ?? null;
  const insights = attributes?.insights ?? null;
  const featureImportance = attributes?.feature_importance ?? null;
  const labelMapping = attributes?.label_mapping ?? null;
  const inputSchema = attributes?.input_schema ?? null;

  const handleRefresh = async () => {
    await client.invalidateQueries({
      queryKey: overviewQueryKeys.attributes(
        projectId,
        isPreview ? "preview" : (versionId ?? ""),
      ),
    });
    await client.invalidateQueries({
      queryKey: previewKeys.detail(projectId),
    });
  };

  const removeMutation = useMutation({
    mutationFn: async (kind: PreviewSingleAssetKind) => {
      return await removePreviewAsset(projectId, kind);
    },
    onSuccess: (_, kind) => {
      const removedTitle = removingAttribute?.title || kind;
      setRemovingAttribute(null);
      toast.success(t("workflow.attributeRemoved", { name: removedTitle }));
      void handleRefresh();
    },
    onError: (err) => {
      setRemovingAttribute(null);
      toast.error(getApiErrorMessage(err, t("workflow.removeFailed")));
    },
  });

  const getArtifactFilename = (kind: string): string | undefined => {
    return attributes?.artifacts?.find((a) => a.kind === kind)?.name;
  };

  return (
    <div role="tabpanel" className="space-y-6">
      {/* Row 1 (2 cols): Feature Importance (50%) + Label Mapping (50%) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 items-stretch">
        <FeatureImportanceCard
          featureImportance={featureImportance}
          insights={insights}
          summarySource={attributes?.summary_sources?.feature_importance}
          filename={
            getArtifactFilename("feature_importance") ||
            getArtifactFilename("insights")
          }
          projectId={projectId}
          versionId={versionId}
          isPreview={isPreview}
          onRequestRemove={() =>
            setRemovingAttribute({
              kind: "feature_importance",
              title: t("workflow.featureImportanceTitle"),
            })
          }
          onRefresh={handleRefresh}
        />
        <LabelMappingCard
          labelMapping={labelMapping}
          filename={
            labelMapping?.filename || getArtifactFilename("label_mapping")
          }
          projectId={projectId}
          versionId={versionId}
          isPreview={isPreview}
          onRequestRemove={() =>
            setRemovingAttribute({
              kind: "label_mapping",
              title: t("workflow.labelMappingTitle"),
            })
          }
          onRefresh={handleRefresh}
        />
      </div>
      
      {/* Row 2 (2 cols): Evaluation Metrics (50%) + Hyperparameters (50%) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 items-stretch">
        <MetricsCard
          metrics={metrics}
          summarySources={attributes?.summary_sources?.metrics}
          filename={getArtifactFilename("metrics")}
          projectId={projectId}
          versionId={versionId}
          isPreview={isPreview}
          onRequestRemove={() =>
            setRemovingAttribute({
              kind: "metrics",
              title: t("workflow.metricsTitle"),
            })
          }
          onRefresh={handleRefresh}
        />
        <HyperparametersCard
          params={params}
          summarySources={attributes?.summary_sources?.params}
          filename={getArtifactFilename("params")}
          projectId={projectId}
          versionId={versionId}
          isPreview={isPreview}
          onRequestRemove={() =>
            setRemovingAttribute({
              kind: "params",
              title: t("workflow.paramsTitle"),
            })
          }
          onRefresh={handleRefresh}
        />
      </div>

      {/* Row 3 (1 col - Full Width 100%): Input Schema */}
      <InputSchemaCard
        inputSchema={inputSchema}
        filename={
          inputSchema?.filename || getArtifactFilename("input_schema")
        }
        projectId={projectId}
        versionId={versionId}
        isPreview={isPreview}
        onRequestRemove={() =>
          setRemovingAttribute({
            kind: "input_schema",
            title: t("workflow.inputSchemaTitle"),
          })
        }
        onRefresh={handleRefresh}
      />

      {/* Row 4 (1 col - Full Width 100%): Model Insights */}
      <InsightsCard
        insights={insights}
        summarySource={attributes?.summary_sources?.model_insights}
        filename={
          getArtifactFilename("model_insights") ||
          getArtifactFilename("insights")
        }
        projectId={projectId}
        versionId={versionId}
        isPreview={isPreview}
        onRequestRemove={() =>
          setRemovingAttribute({
            kind: "model_insights",
            title: t("workflow.insightsTitle"),
          })
        }
        onRefresh={handleRefresh}
      />

      {/* Supplemental summaries (registered source) */}
      {(["model_insights", "feature_importance"] as const).map((kind) =>
        attributes?.summary_sources?.[kind] === "registered" &&
        attributes.supplemental_summaries?.[kind] !== undefined ? (
          <section key={kind} className="space-y-3">
            <h3 className="text-style-heading text-color-foreground">
              {t(
                kind === "model_insights"
                  ? "workflow.insightsTitle"
                  : "workflow.featureImportanceTitle",
              )}
              {" · "}
              {t("workflow.supplementalSource")}
            </h3>
            <pre className="max-h-80 overflow-auto rounded-surface border border-border bg-muted p-4 font-mono text-style-caption text-color-foreground">
              {JSON.stringify(attributes.supplemental_summaries[kind], null, 2)}
            </pre>
          </section>
        ) : null,
      )}

      {/* Confirm remove attribute dialog */}
      <ConfirmDialog
        open={Boolean(removingAttribute)}
        title={t("workflow.removeAttributeConfirmTitle", {
          name: removingAttribute?.title,
        })}
        description={t("workflow.removeAttributeConfirmDesc", {
          name: removingAttribute?.title,
        })}
        confirmText={t("workflow.removeAttribute")}
        tone="danger"
        loading={removeMutation.isPending}
        onCancel={() => setRemovingAttribute(null)}
        onConfirm={() => {
          if (removingAttribute) {
            removeMutation.mutate(removingAttribute.kind);
          }
        }}
      />
    </div>
  );
}

export default ModelAttributesView;
