import { useRunningAttributes } from "@/features/overview/hooks/useProjectOverview";
import type { ModelVersion } from "@/features/projects/types";
import { FeatureImportanceCard } from "@/features/overview/components/FeatureImportanceCard";
import { HyperparametersCard } from "@/features/overview/components/HyperparametersCard";
import { InputSchemaCard } from "@/features/overview/components/InputSchemaCard";
import { InsightsCard } from "@/features/overview/components/InsightsCard";
import { LabelMappingCard } from "@/features/overview/components/LabelMappingCard";
import { MetricsCard } from "@/features/overview/components/MetricsCard";
import { AttributeDropzoneCard } from "@/features/evolution/components/AttributeDropzone";
import {
  BarChart2,
  Database,
  Gauge,
  Lightbulb,
  SlidersHorizontal,
  Tags,
} from "lucide-react";
import { useTranslation } from "react-i18next";

export interface AttributesEvolutionPageProps {
  projectId: string;
  version: ModelVersion;
}

export function AttributesEvolutionPage({
  projectId,
  version,
}: AttributesEvolutionPageProps) {
  const { t } = useTranslation("evolution");
  const { t: tOverview } = useTranslation("overview");

  const { data: attributes, isLoading } = useRunningAttributes(
    projectId,
    version.id,
  );

  const metrics =
    attributes?.metrics ??
    (Object.keys(version.metrics_summary || {}).length > 0
      ? version.metrics_summary
      : null);

  const params =
    attributes?.params ??
    (Object.keys(version.params_summary || {}).length > 0
      ? version.params_summary
      : null);

  const insights =
    attributes?.insights ??
    ((version.insights_summary?.items?.length ?? 0) > 0
      ? version.insights_summary
      : null);

  const featureImportance = attributes?.feature_importance ?? null;
  const labelMapping = attributes?.label_mapping ?? null;
  const inputSchema = attributes?.input_schema ?? null;

  const hasMetrics = Boolean(metrics && Object.keys(metrics).length > 0);
  const hasParams = Boolean(params && Object.keys(params).length > 0);
  const hasInsights = Boolean(
    insights &&
      (Array.isArray(insights.items)
        ? insights.items.length > 0
        : Object.keys(insights).length > 0),
  );
  const hasFeatureImportance = Boolean(
    featureImportance &&
      ((featureImportance.items && featureImportance.items.length > 0) ||
        Object.keys(featureImportance).length > 0),
  );
  const hasLabelMapping = Boolean(
    labelMapping &&
      ((Array.isArray(labelMapping.mapping) && labelMapping.mapping.length > 0) ||
        (labelMapping.mapping &&
          typeof labelMapping.mapping === "object" &&
          Object.keys(labelMapping.mapping).length > 0)),
  );
  const hasInputSchema = Boolean(
    inputSchema &&
      Boolean(inputSchema.schema),
  );

  const getArtifactFilename = (kind: string): string | undefined => {
    return (
      attributes?.artifacts?.find((a) => a.kind === kind)?.name ||
      version.artifacts.find((a) => a.kind === kind)?.name
    );
  };

  if (isLoading && !attributes) {
    return (
      <div className="rounded-surface border border-border bg-surface p-12 text-center text-color-muted-foreground">
        {t("workspace.loading", "Loading attributes...")}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Row 1: Feature Importance (50%) + Label Mapping (50%) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 items-stretch">
        {hasFeatureImportance ? (
          <FeatureImportanceCard
            featureImportance={featureImportance}
            insights={insights}
            summarySource={attributes?.summary_sources?.feature_importance}
            filename={
              getArtifactFilename("feature_importance") ||
              getArtifactFilename("insights")
            }
            projectId={projectId}
            versionId={version.id}
            isPreview={false}
          />
        ) : (
          <AttributeDropzoneCard
            kind="feature_importance"
            title={tOverview("workflow.featureImportanceTitle")}
            hint={tOverview("workflow.featureImportanceHint")}
            icon={<BarChart2 className="h-5 w-5 text-color-primary" />}
            versionId={version.id}
            projectId={projectId}
          />
        )}

        {hasLabelMapping ? (
          <LabelMappingCard
            labelMapping={labelMapping}
            filename={getArtifactFilename("label_mapping")}
            projectId={projectId}
            versionId={version.id}
            isPreview={false}
          />
        ) : (
          <AttributeDropzoneCard
            kind="label_mapping"
            title={tOverview("workflow.labelMappingTitle")}
            hint={tOverview("workflow.labelMappingHint")}
            icon={<Tags className="h-5 w-5 text-color-primary" />}
            versionId={version.id}
            projectId={projectId}
          />
        )}
      </div>

      {/* Row 2: Input Schema (50%) + Model Insights (50%) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 items-stretch">
        {hasInputSchema ? (
          <InputSchemaCard
            inputSchema={inputSchema}
            filename={getArtifactFilename("input_schema")}
            projectId={projectId}
            versionId={version.id}
            isPreview={false}
          />
        ) : (
          <AttributeDropzoneCard
            kind="input_schema"
            title={tOverview("workflow.inputSchemaTitle")}
            hint={tOverview("workflow.inputSchemaHint")}
            icon={<Database className="h-5 w-5 text-color-primary" />}
            versionId={version.id}
            projectId={projectId}
          />
        )}

        {hasInsights ? (
          <InsightsCard
            insights={insights}
            filename={getArtifactFilename("model_insights")}
            projectId={projectId}
            versionId={version.id}
            isPreview={false}
          />
        ) : (
          <AttributeDropzoneCard
            kind="model_insights"
            title={tOverview("workflow.insightsTitle")}
            hint={tOverview("workflow.insightsHint")}
            icon={<Lightbulb className="h-5 w-5 text-color-primary" />}
            versionId={version.id}
            projectId={projectId}
          />
        )}
      </div>

      {/* Row 3: Metrics (50%) + Hyperparameters (50%) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 items-stretch">
        {hasMetrics ? (
          <MetricsCard
            metrics={metrics}
            summarySources={attributes?.summary_sources?.metrics}
            filename={getArtifactFilename("metrics")}
            projectId={projectId}
            versionId={version.id}
            isPreview={false}
          />
        ) : (
          <AttributeDropzoneCard
            kind="metrics"
            title={tOverview("workflow.metricsTitle")}
            hint={tOverview("workflow.metricsHint")}
            icon={<Gauge className="h-5 w-5 text-color-primary" />}
            versionId={version.id}
            projectId={projectId}
          />
        )}

        {hasParams ? (
          <HyperparametersCard
            params={params}
            summarySources={attributes?.summary_sources?.params}
            filename={getArtifactFilename("params")}
            projectId={projectId}
            versionId={version.id}
            isPreview={false}
          />
        ) : (
          <AttributeDropzoneCard
            kind="params"
            title={tOverview("workflow.paramsTitle")}
            hint={tOverview("workflow.paramsHint")}
            icon={<SlidersHorizontal className="h-5 w-5 text-color-primary" />}
            versionId={version.id}
            projectId={projectId}
          />
        )}
      </div>
    </div>
  );
}

export { AttributesEvolutionPage as EvolutionAttributesTab };

