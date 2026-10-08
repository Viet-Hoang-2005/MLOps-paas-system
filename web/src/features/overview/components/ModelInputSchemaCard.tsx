import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { StepTitle } from "@/shared/components/StepTitle";
import { toast } from "@/shared/types/toastStore";
import {
  Check,
  Code2,
  Copy,
  FileCode,
  Table,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AttributeDropzoneCard,
  AttributeMissingVersionCard,
} from "./AttributeEmptyStateCards";

export interface ParsedSchemaField {
  name: string;
  type: string;
  required?: boolean;
  description?: string;
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

export interface ModelInputSchemaCardProps {
  inputSchema?: { filename?: string; schema?: unknown } | null;
  filename?: string;
  projectId: string;
  versionId?: string;
  isPreview?: boolean;
  onRequestRemove?: () => void;
  onRefresh?: () => void;
  className?: string;
}

export function ModelInputSchemaCard({
  inputSchema,
  filename,
  projectId,
  versionId,
  isPreview = false,
  onRequestRemove,
  onRefresh,
  className = "",
}: ModelInputSchemaCardProps) {
  const { t } = useTranslation("overview");
  const [schemaRawView, setSchemaRawView] = useState(false);
  const [copiedSchema, setCopiedSchema] = useState(false);

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

  const hasInputSchema = Boolean(inputSchema?.schema);

  if (!hasInputSchema) {
    if (isPreview) {
      return (
        <AttributeDropzoneCard
          kind="input_schema"
          accept=".json"
          title={t("workflow.inputSchemaTitle")}
          hint={t("workflow.inputSchemaHint")}
          icon={<Table className="h-5 w-5 text-color-primary" />}
          projectId={projectId}
          onSuccess={onRefresh ?? (() => {})}
          className={className}
        />
      );
    }
    return (
      <AttributeMissingVersionCard
        title={t("workflow.inputSchemaTitle")}
        hint={t("workflow.missingAttributeInVersionHint")}
        icon={<Table className="h-5 w-5 text-color-primary" />}
        projectId={projectId}
        versionId={versionId}
        className={className}
      />
    );
  }

  const effectiveFilename = filename || inputSchema?.filename;

  return (
    <section
      className={`rounded-surface border border-border bg-surface p-6 flex flex-col justify-between ${className}`}
    >
      <div>
        <StepTitle
          icon={<Table className="h-5 w-5 text-color-primary" />}
          title={t("workflow.inputSchemaTitle")}
          className="mb-6"
          action={
            <div className="flex items-center gap-2 flex-wrap">
              {effectiveFilename && (
                <Badge
                  variant="neutral"
                  className="font-mono text-style-caption text-color-muted-foreground"
                >
                  <FileCode className="h-3.5 w-3.5" />
                  <span>{effectiveFilename}</span>
                </Badge>
              )}
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
      </div>
    </section>
  );
}

export default ModelInputSchemaCard;

