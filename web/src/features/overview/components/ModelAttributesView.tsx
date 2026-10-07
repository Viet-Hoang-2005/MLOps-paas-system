import type {
  ModelAttributesResponse,
  ModelInsightItem,
} from "@/shared/api/catalogApi";
import { formatNumber } from "@/shared/i18n/formatters";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { StepTitle } from "@/shared/components/StepTitle";
import { toast } from "@/shared/types/toastStore";
import { getApiErrorMessage } from "@/shared/api/errors";
import {
  uploadPreviewSingleAsset,
  removePreviewAsset,
  type PreviewSingleAssetKind,
} from "@/features/projects/api/previewApi";
import {
  addSupplementalArtifacts,
  type SupplementalArtifactsPayload,
} from "@/features/evolution/api/evolutionApi";
import { overviewQueryKeys } from "@/features/overview/queryKeys";
import { previewKeys } from "@/features/projects/hooks/usePreview";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  Check,
  Code2,
  Copy,
  FileCode,
  Gauge,
  Layers,
  ListTree,
  Lock,
  SlidersHorizontal,
  Table,
  Trash2,
  Upload,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

export interface ModelAttributesViewProps {
  attributes?: ModelAttributesResponse | null;
  projectId: string;
  versionId?: string;
  isPreview?: boolean;
}

interface ParsedSchemaField {
  name: string;
  type: string;
  required?: boolean;
  description?: string;
}

function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function parseSchemaToFields(schema: unknown): ParsedSchemaField[] | null {
  if (!schema) return null;

  if (Array.isArray(schema)) {
    const fields: ParsedSchemaField[] = [];
    for (const item of schema) {
      if (typeof item === "object" && item !== null) {
        const obj = item as Record<string, unknown>;
        const name = String(obj.name ?? obj.column ?? obj.feature ?? "");
        const type = String(obj.type ?? obj.dtype ?? "unknown");
        if (name) {
          fields.push({
            name,
            type,
            required:
              typeof obj.required === "boolean" ? obj.required : undefined,
            description:
              typeof obj.description === "string" ? obj.description : undefined,
          });
        }
      } else if (typeof item === "string") {
        fields.push({ name: item, type: "any" });
      }
    }
    return fields.length > 0 ? fields : null;
  }

  if (typeof schema === "object" && schema !== null) {
    const obj = schema as Record<string, unknown>;

    if (
      obj.properties &&
      typeof obj.properties === "object" &&
      obj.properties !== null
    ) {
      const props = obj.properties as Record<string, unknown>;
      const requiredSet = new Set(
        Array.isArray(obj.required) ? (obj.required as string[]) : [],
      );
      const fields: ParsedSchemaField[] = [];
      for (const [key, propVal] of Object.entries(props)) {
        if (typeof propVal === "object" && propVal !== null) {
          const p = propVal as Record<string, unknown>;
          fields.push({
            name: key,
            type: String(p.type ?? "any"),
            required: requiredSet.has(key),
            description:
              typeof p.description === "string" ? p.description : undefined,
          });
        } else {
          fields.push({
            name: key,
            type: String(propVal),
            required: requiredSet.has(key),
          });
        }
      }
      return fields.length > 0 ? fields : null;
    }

    if (Array.isArray(obj.columns)) {
      return parseSchemaToFields(obj.columns);
    }

    const entries = Object.entries(obj);
    if (
      entries.length > 0 &&
      entries.every(([, v]) => typeof v === "string" || typeof v === "number")
    ) {
      return entries.map(([name, type]) => ({
        name,
        type: String(type),
      }));
    }
  }

  return null;
}

interface AttributeDropzoneCardProps {
  title: string;
  hint: string;
  icon: ReactNode;
  kind: PreviewSingleAssetKind;
  accept: string;
  projectId: string;
  versionId?: string;
  isPreview?: boolean;
  onSuccess: () => void;
}

function AttributeDropzoneCard({
  title,
  hint,
  icon,
  kind,
  accept,
  projectId,
  versionId,
  isPreview,
  onSuccess,
}: AttributeDropzoneCardProps) {
  const { t } = useTranslation("overview");
  const [stagedFile, setStagedFile] = useState<File | null>(null);

  const handleFileChange = (file: File | null) => {
    if (!file) {
      setStagedFile(null);
      return;
    }
    if (file.size === 0) {
      toast.error(t("workflow.emptyFileError"));
      return;
    }
    const lower = file.name.toLowerCase();
    if (kind === "label_mapping") {
      if (!lower.endsWith(".json") && !lower.endsWith(".pkl")) {
        toast.error(t("workflow.invalidLabelMappingFile"));
        return;
      }
    } else {
      if (!lower.endsWith(".json")) {
        toast.error(t("workflow.invalidJsonFile"));
        return;
      }
    }
    setStagedFile(file);
  };

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!stagedFile) return;
      if (isPreview) {
        return await uploadPreviewSingleAsset(projectId, kind, stagedFile);
      }
      if (!versionId) {
        throw new Error(t("workflow.noVersionForUpload"));
      }
      const payloadKey = `${kind}_file` as keyof SupplementalArtifactsPayload;
      return await addSupplementalArtifacts(versionId, {
        [payloadKey]: stagedFile,
      });
    },
    onSuccess: () => {
      setStagedFile(null);
      toast.success(t("workflow.attributeUploaded", { name: title }));
      onSuccess();
    },
    onError: (err) => {
      toast.error(getApiErrorMessage(err, t("workflow.uploadFailed")));
    },
  });

  return (
    <section className="rounded-surface border border-border bg-surface p-6">
      <StepTitle
        icon={icon}
        title={title}
        description={hint}
        badge={
          <Badge variant="neutral">
            {!isPreview && <Lock className="mr-1 inline h-3 w-3" />}
            {isPreview
              ? t("workflow.uploadPreviewNoticeTitle")
              : t("workflow.uploadImmutableNoticeTitle")}
          </Badge>
        }
        className="mb-6"
      />

      <div className="space-y-4">
        <FileDropzone
          accept={accept}
          disabled={uploadMutation.isPending || (!isPreview && !versionId)}
          title={
            stagedFile
              ? stagedFile.name
              : t("workflow.selectAttributeFile", { name: title })
          }
          subtitle={stagedFile ? formatBytes(stagedFile.size) : hint}
          hasFile={Boolean(stagedFile)}
          onRemove={() => setStagedFile(null)}
          onChange={handleFileChange}
        />

        {stagedFile && (
          <div className="flex items-center justify-between rounded-surface border border-border bg-muted p-3">
            <div className="flex items-center gap-2 truncate">
              {icon}
              <span className="truncate font-mono text-style-body-sm text-color-foreground">
                {stagedFile.name}
              </span>
              <span className="text-style-caption text-color-muted-foreground">
                ({formatBytes(stagedFile.size)})
              </span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button
                size="sm"
                variant="ghost"
                disabled={uploadMutation.isPending}
                onClick={() => setStagedFile(null)}
              >
                {t("workflow.clear")}
              </Button>
              <Button
                size="sm"
                variant="primary"
                icon={<Upload className="h-4 w-4" />}
                loading={uploadMutation.isPending}
                disabled={!isPreview && !versionId}
                onClick={() => uploadMutation.mutate()}
              >
                {t("workflow.upload")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export function ModelAttributesView({
  attributes,
  projectId,
  versionId,
  isPreview = false,
}: ModelAttributesViewProps) {
  const { t, i18n } = useTranslation("overview");
  const client = useQueryClient();
  const [showAllInsights, setShowAllInsights] = useState(false);
  const [schemaRawView, setSchemaRawView] = useState(false);
  const [copiedSchema, setCopiedSchema] = useState(false);
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
      queryKey: overviewQueryKeys.attributes(projectId, versionId ?? ""),
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

  const parsedSchemaFields = useMemo(() => {
    return parseSchemaToFields(inputSchema?.schema);
  }, [inputSchema]);

  const handleCopySchema = async () => {
    if (!inputSchema?.schema) return;
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(inputSchema.schema, null, 2),
      );
      setCopiedSchema(true);
      toast.success(t("workflow.schemaCopied"));
      setTimeout(() => setCopiedSchema(false), 2000);
    } catch {
      // ignore
    }
  };

  const hasMetrics = Boolean(metrics && Object.keys(metrics).length > 0);
  const hasParams = Boolean(params && Object.keys(params).length > 0);
  const hasLabelMapping = Boolean(
    labelMapping?.mapping && labelMappingEntries.length > 0,
  );
  const hasInputSchema = Boolean(inputSchema?.schema);
  const hasFeatureImportance = Boolean(insightItems.length > 0);
  const hasInsights = Boolean(
    insights &&
      typeof insights === "object" &&
      Object.keys(insights).length > 0 &&
      !(insights.kind === "feature_importance" && Object.keys(insights).length <= 2),
  );

  return (
    <div role="tabpanel" className="space-y-6">
      {/* 1. Evaluation Metrics */}
      {hasMetrics ? (
        <section className="rounded-surface border border-border bg-surface p-6">
          <StepTitle
            icon={<Gauge className="h-5 w-5 text-color-primary" />}
            title={t("workflow.metricsTitle")}
            className="mb-6"
            action={
              isPreview ? (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Trash2 className="h-3.5 w-3.5 text-color-danger" />}
                  onClick={() =>
                    setRemovingAttribute({
                      kind: "metrics",
                      title: t("workflow.metricsTitle"),
                    })
                  }
                >
                  {t("workflow.removeAttribute")}
                </Button>
              ) : undefined
            }
          />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
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
        </section>
      ) : (
        <AttributeDropzoneCard
          kind="metrics"
          accept=".json"
          title={t("workflow.metricsTitle")}
          hint={t("workflow.metricsHint")}
          icon={<Gauge className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          versionId={versionId}
          isPreview={isPreview}
          onSuccess={handleRefresh}
        />
      )}

      {/* 2. Hyperparameters */}
      {hasParams ? (
        <section className="rounded-surface border border-border bg-surface p-6">
          <StepTitle
            icon={<SlidersHorizontal className="h-5 w-5 text-color-primary" />}
            title={t("workflow.paramsTitle")}
            className="mb-6"
            action={
              isPreview ? (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Trash2 className="h-3.5 w-3.5 text-color-danger" />}
                  onClick={() =>
                    setRemovingAttribute({
                      kind: "params",
                      title: t("workflow.paramsTitle"),
                    })
                  }
                >
                  {t("workflow.removeAttribute")}
                </Button>
              ) : undefined
            }
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
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
                <div
                  className="mt-1 truncate font-mono text-style-body text-color-foreground"
                  title={String(val)}
                >
                  {typeof val === "object" ? JSON.stringify(val) : String(val)}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <AttributeDropzoneCard
          kind="params"
          accept=".json"
          title={t("workflow.paramsTitle")}
          hint={t("workflow.paramsHint")}
          icon={<SlidersHorizontal className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          versionId={versionId}
          isPreview={isPreview}
          onSuccess={handleRefresh}
        />
      )}

      {/* 3. Label Mapping */}
      {hasLabelMapping ? (
        <section className="rounded-surface border border-border bg-surface p-6">
          <StepTitle
            icon={<ListTree className="h-5 w-5 text-color-primary" />}
            title={
              <span className="flex items-center gap-2">
                <span>{t("workflow.labelMappingTitle")}</span>
                {labelMapping?.filename && (
                  <span className="font-mono text-style-caption text-color-muted-foreground">
                    ({labelMapping.filename})
                  </span>
                )}
              </span>
            }
            className="mb-6"
            action={
              isPreview ? (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Trash2 className="h-3.5 w-3.5 text-color-danger" />}
                  onClick={() =>
                    setRemovingAttribute({
                      kind: "label_mapping",
                      title: t("workflow.labelMappingTitle"),
                    })
                  }
                >
                  {t("workflow.removeAttribute")}
                </Button>
              ) : undefined
            }
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {labelMappingEntries.map(([k, v]) => (
              <div
                key={k}
                className="flex items-center justify-between rounded-surface border border-border bg-muted px-4 py-2.5"
              >
                <span className="font-mono text-style-body font-medium text-color-foreground">
                  {k}
                </span>
                <span className="text-style-caption text-color-muted-foreground">
                  →
                </span>
                <span className="font-mono text-style-body font-semibold text-color-foreground">
                  {v}
                </span>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <AttributeDropzoneCard
          kind="label_mapping"
          accept=".json,.pkl"
          title={t("workflow.labelMappingTitle")}
          hint={t("workflow.labelMappingHint")}
          icon={<ListTree className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          versionId={versionId}
          isPreview={isPreview}
          onSuccess={handleRefresh}
        />
      )}

      {/* 4. Input Schema */}
      {hasInputSchema ? (
        <section className="rounded-surface border border-border bg-surface p-6">
          <StepTitle
            icon={<Table className="h-5 w-5 text-color-primary" />}
            title={
              <span className="flex items-center gap-2">
                <span>{t("workflow.inputSchemaTitle")}</span>
                {inputSchema?.filename && (
                  <span className="font-mono text-style-caption text-color-muted-foreground">
                    ({inputSchema.filename})
                  </span>
                )}
              </span>
            }
            className="mb-6"
            action={
              <div className="flex items-center gap-2">
                {Boolean(parsedSchemaFields) && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setSchemaRawView(!schemaRawView)}
                  >
                    {schemaRawView ? (
                      <>
                        <Table className="mr-1.5 h-3.5 w-3.5" />
                        {t("workflow.inputSchemaTitle")}
                      </>
                    ) : (
                      <>
                        <FileCode className="mr-1.5 h-3.5 w-3.5" />
                        <Code2 className="h-3.5 w-3.5" />
                      </>
                    )}
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopySchema}
                >
                  {copiedSchema ? (
                    <Check className="mr-1.5 h-3.5 w-3.5" />
                  ) : (
                    <Copy className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  {t("workflow.copySchema")}
                </Button>
                {isPreview && (
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Trash2 className="h-3.5 w-3.5 text-color-danger" />}
                    onClick={() =>
                      setRemovingAttribute({
                        kind: "input_schema",
                        title: t("workflow.inputSchemaTitle"),
                      })
                    }
                  >
                    {t("workflow.removeAttribute")}
                  </Button>
                )}
              </div>
            }
          />

          {!schemaRawView && parsedSchemaFields ? (
            <div className="overflow-x-auto rounded-surface border border-border">
              <table className="w-full text-left text-style-caption">
                <thead className="bg-muted text-style-caption-strong text-color-foreground">
                  <tr>
                    <th className="px-4 py-2.5">
                      {t("workflow.schemaField")}
                    </th>
                    <th className="px-4 py-2.5">{t("workflow.schemaType")}</th>
                    <th className="px-4 py-2.5">
                      {t("workflow.schemaRequired")}
                    </th>
                    <th className="px-4 py-2.5">
                      {t("workflow.schemaDescription")}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border bg-surface">
                  {parsedSchemaFields.map((field) => (
                    <tr key={field.name}>
                      <td className="px-4 py-2.5 font-mono text-color-foreground">
                        {field.name}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-color-muted-foreground">
                        {field.type}
                      </td>
                      <td className="px-4 py-2.5 text-color-muted-foreground">
                        {field.required === undefined
                          ? "—"
                          : field.required
                            ? t("workflow.schemaRequired")
                            : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-color-muted-foreground">
                        {field.description ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <pre className="max-h-80 overflow-auto rounded-surface border border-border bg-muted p-4 font-mono text-style-caption text-color-foreground">
              {JSON.stringify(inputSchema?.schema, null, 2)}
            </pre>
          )}
        </section>
      ) : (
        <AttributeDropzoneCard
          kind="input_schema"
          accept=".json"
          title={t("workflow.inputSchemaTitle")}
          hint={t("workflow.inputSchemaHint")}
          icon={<Table className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          versionId={versionId}
          isPreview={isPreview}
          onSuccess={handleRefresh}
        />
      )}

      {/* 5. Feature Importance */}
      {hasFeatureImportance ? (
        <section className="rounded-surface border border-border bg-surface p-6">
          <StepTitle
            icon={<BarChart3 className="h-5 w-5 text-color-primary" />}
            title={
              <span className="flex items-center gap-2">
                <span>{t("workflow.featureImportanceTitle")}</span>
                <span className="text-style-caption text-color-muted-foreground">
                  ({t("workflow.totalFeatures")}: {insightItems.length})
                </span>
              </span>
            }
            className="mb-6"
            action={
              <div className="flex items-center gap-2">
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
                {isPreview && (
                  <Button
                    size="sm"
                    variant="secondary"
                    icon={<Trash2 className="h-3.5 w-3.5 text-color-danger" />}
                    onClick={() =>
                      setRemovingAttribute({
                        kind: "feature_importance",
                        title: t("workflow.featureImportanceTitle"),
                      })
                    }
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
        </section>
      ) : (
        <AttributeDropzoneCard
          kind="feature_importance"
          accept=".json"
          title={t("workflow.featureImportanceTitle")}
          hint={t("workflow.featureImportanceHint")}
          icon={<BarChart3 className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          versionId={versionId}
          isPreview={isPreview}
          onSuccess={handleRefresh}
        />
      )}

      {/* 6. Model Insights */}
      {hasInsights ? (
        <section className="rounded-surface border border-border bg-surface p-6">
          <StepTitle
            icon={<Layers className="h-5 w-5 text-color-primary" />}
            title={t("workflow.insightsTitle")}
            className="mb-6"
            action={
              isPreview ? (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Trash2 className="h-3.5 w-3.5 text-color-danger" />}
                  onClick={() =>
                    setRemovingAttribute({
                      kind: "model_insights",
                      title: t("workflow.insightsTitle"),
                    })
                  }
                >
                  {t("workflow.removeAttribute")}
                </Button>
              ) : undefined
            }
          />
          <pre className="max-h-80 overflow-auto rounded-surface border border-border bg-muted p-4 font-mono text-style-caption text-color-foreground">
            {JSON.stringify(insights, null, 2)}
          </pre>
        </section>
      ) : (
        <AttributeDropzoneCard
          kind="model_insights"
          accept=".json"
          title={t("workflow.insightsTitle")}
          hint={t("workflow.insightsHint")}
          icon={<Layers className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          versionId={versionId}
          isPreview={isPreview}
          onSuccess={handleRefresh}
        />
      )}

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
