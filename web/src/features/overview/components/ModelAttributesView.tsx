import type {
  ModelAttributesResponse,
  ModelInsightItem,
} from "@/shared/api/catalogApi";
import { formatNumber } from "@/shared/i18n/formatters";
import { Button } from "@/shared/components/Button";
import { Placeholder } from "@/shared/components/Placeholder";
import { toast } from "@/shared/types/toastStore";
import {
  Check,
  Code2,
  Copy,
  FileCode,
  Gauge,
  Layers,
  ListTree,
  SlidersHorizontal,
  Table,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

export interface ModelAttributesViewProps {
  attributes?: ModelAttributesResponse | null;
  projectId: string;
}

interface ParsedSchemaField {
  name: string;
  type: string;
  required?: boolean;
  description?: string;
}

function parseSchemaToFields(schema: unknown): ParsedSchemaField[] | null {
  if (!schema) return null;

  // 1. Array of column definitions: [{ name, type, ... }]
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
            required: typeof obj.required === "boolean" ? obj.required : undefined,
            description: typeof obj.description === "string" ? obj.description : undefined,
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

    // 2. Standard JSON Schema with properties: { properties: { col1: { type } }, required: [...] }
    if (obj.properties && typeof obj.properties === "object" && obj.properties !== null) {
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
            description: typeof p.description === "string" ? p.description : undefined,
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

    // 3. Object with columns array: { columns: [...] }
    if (Array.isArray(obj.columns)) {
      return parseSchemaToFields(obj.columns);
    }

    // 4. Object as simple key-value pairs: { "feature_1": "float64", "feature_2": "int" }
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

export function ModelAttributesView({
  attributes,
}: ModelAttributesViewProps) {
  const { t, i18n } = useTranslation("overview");
  const [showAllInsights, setShowAllInsights] = useState(false);
  const [schemaRawView, setSchemaRawView] = useState(false);
  const [copiedSchema, setCopiedSchema] = useState(false);

  const metrics = attributes?.metrics ?? null;
  const params = attributes?.params ?? null;
  const insights = attributes?.insights ?? null;
  const labelMapping = attributes?.label_mapping ?? null;
  const inputSchema = attributes?.input_schema ?? null;

  const hasAnyData = Boolean(
    (metrics && Object.keys(metrics).length > 0) ||
      (params && Object.keys(params).length > 0) ||
      (insights?.items && insights.items.length > 0) ||
      labelMapping?.mapping ||
      inputSchema?.schema,
  );

  const insightItems: ModelInsightItem[] = useMemo(() => {
    if (!insights?.items) return [];
    return [...insights.items]
      .filter((item) => Number.isFinite(item.value))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  }, [insights]);

  const maxInsightValue = useMemo(() => {
    if (insightItems.length === 0) return 1;
    return Math.max(...insightItems.map((item) => Math.abs(item.value)), 1e-10);
  }, [insightItems]);

  const displayedInsights = showAllInsights
    ? insightItems
    : insightItems.slice(0, 10);

  const labelMappingEntries = useMemo<[string, string][]>(() => {
    if (!labelMapping?.mapping) return [];
    if (Array.isArray(labelMapping.mapping)) {
      return labelMapping.mapping.map((val, idx) => [String(idx), String(val)]);
    }
    if (typeof labelMapping.mapping === "object" && labelMapping.mapping !== null) {
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

  if (!attributes || !hasAnyData) {
    return (
      <Placeholder
        role="tabpanel"
        title={t("workflow.attributes")}
        description={t("workflow.noAttributes")}
        icon={<SlidersHorizontal className="h-6 w-6" />}
        className="flex-1 min-h-105"
      />
    );
  }

  return (
    <div role="tabpanel" className="space-y-6">
      {/* 1. Evaluation Metrics */}
      {metrics && Object.keys(metrics).length > 0 && (
        <section className="rounded-surface border border-border bg-surface p-6">
          <div className="mb-4 flex items-center gap-2">
            <Gauge className="h-5 w-5 text-color-primary" />
            <h2 className="text-style-heading text-color-foreground">
              {t("workflow.metricsTitle")}
            </h2>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {Object.entries(metrics).map(([key, val]) => {
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
      )}

      {/* 2. Feature Importance & Model Insights */}
      {insightItems.length > 0 && (
        <section className="rounded-surface border border-border bg-surface p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Layers className="h-5 w-5 text-color-primary" />
              <h2 className="text-style-heading text-color-foreground">
                {t("workflow.featureImportanceTitle")}
              </h2>
              <span className="text-style-caption text-color-muted-foreground">
                ({t("workflow.totalFeatures")}: {insightItems.length})
              </span>
            </div>
            {insightItems.length > 10 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowAllInsights(!showAllInsights)}
              >
                {showAllInsights
                  ? t("workflow.showTopFeatures", { count: 10 })
                  : t("workflow.showAllFeatures", { count: insightItems.length })}
              </Button>
            )}
          </div>

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
      )}

      {/* 3. Label Mapping (Neutral Key-Value Display, NO semantic badges) */}
      {labelMappingEntries.length > 0 && (
        <section className="rounded-surface border border-border bg-surface p-6">
          <div className="mb-4 flex items-center gap-2">
            <ListTree className="h-5 w-5 text-color-primary" />
            <h2 className="text-style-heading text-color-foreground">
              {t("workflow.labelMappingTitle")}
            </h2>
            {labelMapping?.filename && (
              <span className="font-mono text-style-caption text-color-muted-foreground">
                ({labelMapping.filename})
              </span>
            )}
          </div>
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
      )}

      {/* 4. Hyperparameters */}
      {params && Object.keys(params).length > 0 && (
        <section className="rounded-surface border border-border bg-surface p-6">
          <div className="mb-4 flex items-center gap-2">
            <SlidersHorizontal className="h-5 w-5 text-color-primary" />
            <h2 className="text-style-heading text-color-foreground">
              {t("workflow.paramsTitle")}
            </h2>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {Object.entries(params).map(([key, val]) => (
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
      )}

      {/* 5. Input Schema */}
      {Boolean(inputSchema?.schema) && (
        <section className="rounded-surface border border-border bg-surface p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Table className="h-5 w-5 text-color-primary" />
              <h2 className="text-style-heading text-color-foreground">
                {t("workflow.inputSchemaTitle")}
              </h2>
              {inputSchema?.filename && (
                <span className="font-mono text-style-caption text-color-muted-foreground">
                  ({inputSchema.filename})
                </span>
              )}
            </div>
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
            </div>
          </div>

          {!schemaRawView && parsedSchemaFields ? (
            <div className="overflow-x-auto rounded-surface border border-border">
              <table className="w-full text-left text-style-caption">
                <thead className="bg-muted text-style-caption-strong text-color-foreground">
                  <tr>
                    <th className="px-4 py-2.5">{t("workflow.schemaField")}</th>
                    <th className="px-4 py-2.5">{t("workflow.schemaType")}</th>
                    <th className="px-4 py-2.5">{t("workflow.schemaRequired")}</th>
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
      )}
    </div>
  );
}

