import { ApiKeyDialog } from "@/features/api-keys/components/ApiKeyDialog";
import { useApiKeyForm } from "@/features/api-keys/hooks/useApiKeyForm";
import { useApiTokens } from "@/features/api-keys/hooks/useApiTokens";
import type { APIKeyRecord } from "@/features/api-keys/types";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import type { ModelProject } from "@/features/projects/types";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Input } from "@/shared/components/Input";
import { PageHeader } from "@/shared/components/PageHeader";
import { Table } from "@/shared/components/Table";
import { TextArea } from "@/shared/components/TextArea";
import { Title } from "@/shared/components/Title";
import { toast } from "@/shared/types/toastStore";
import type { ColumnDef } from "@tanstack/react-table";
import { Copy } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

export default function ApiKeyPage() {
  const { t } = useTranslation("settings");
  const { keyId } = useParams<{ keyId?: string }>();
  const navigate = useNavigate();
  const { apiKeys } = useApiTokens();

  const editingKey = useMemo<APIKeyRecord | null>(() => {
    if (!keyId) return null;
    return apiKeys.find((key: APIKeyRecord) => key.id === keyId) || null;
  }, [keyId, apiKeys]);

  const {
    apiKeyName,
    setApiKeyName,
    apiKeyDescription,
    setApiKeyDescription,
    setApiKeyScope,
    apiKeyModels,
    setApiKeyModels,
    createdApiKey,
    setCreatedApiKey,
    handleSaveAPIKey,
    saving,
  } = useApiKeyForm(editingKey);

  const { data: modelsData } = useModelProjects();

  const handleCopyCreatedKey = async () => {
    if (!createdApiKey?.api_key) return;
    try {
      await navigator.clipboard.writeText(createdApiKey.api_key);
      toast.success(t("apiKey.copied"));
    } catch {
      toast.warning(t("apiKey.copyFailed"));
    }
  };

  const handleDone = () => {
    setCreatedApiKey(null);
    navigate("/dashboard/api-keys");
  };

  const privateModels = useMemo(() => {
    const models = modelsData?.models || [];
    return models.filter((m) => m.access_mode === "private");
  }, [modelsData?.models]);

  const columns: ColumnDef<ModelProject>[] = [
    {
      id: "selected",
      header: t("apiKey.use"),
      enableSorting: false,
      cell: ({ row }) => (
        <input
          type="checkbox"
          aria-label={t("apiKey.allowModel", { name: row.original.name })}
          className="h-4 w-4 rounded-compact border-input accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          checked={apiKeyModels.includes(row.original.id)}
          onChange={(event) => {
            const nextIds = event.target.checked
              ? [...apiKeyModels, row.original.id]
              : apiKeyModels.filter((id) => id !== row.original.id);
            setApiKeyModels(nextIds);
            setApiKeyScope("specific");
          }}
        />
      ),
    },
    {
      accessorKey: "name",
      header: t("apiKey.name"),
      cell: ({ row }) => (
        <span className="font-semibold text-color-foreground">
          {row.original.name}
        </span>
      ),
    },
    {
      accessorKey: "flavor",
      header: t("apiKey.flavor"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap text-color-foreground">
          {row.original.flavor || "—"}
        </span>
      ),
    },
    {
      accessorKey: "access_mode",
      header: t("apiKey.accessMode"),
      cell: ({ row }) => (
        <Badge variant="neutral">
          {row.original.access_mode === "private"
            ? t("apiKey.private")
            : t("apiKey.public")}
        </Badge>
      ),
    },
    {
      accessorKey: "lifecycle_status",
      header: t("apiKey.modelStatus"),
      cell: ({ row }) => {
        const deletionState = row.original.deletion_state;
        const lifecycleStatus = row.original.lifecycle_status ?? "registered";
        const variant =
          deletionState === "delete_failed"
            ? "danger"
            : deletionState === "deleting"
              ? "warning"
              : lifecycleStatus === "running"
                ? "success"
                : "neutral";

        const label =
          deletionState === "delete_failed"
            ? t("apiKey.modelDeleteFailed")
            : deletionState === "deleting"
              ? t("apiKey.deleting")
              : lifecycleStatus === "running"
                ? t("apiKey.running")
                : lifecycleStatus === "preview"
                  ? t("apiKey.preview")
                  : t("apiKey.registered");

        return <Badge variant={variant}>{label}</Badge>;
      },
    },
    {
      accessorKey: "description",
      header: t("apiKey.description"),
      cell: ({ row }) => (
        <span className="text-color-muted-foreground">
          {row.original.description || t("apiKey.noDescription")}
        </span>
      ),
    },
  ];

  return (
    <div className="flex w-full flex-col space-y-6">
      <PageHeader
        title={keyId ? t("apiKey.editTitle") : t("apiKey.createTitle")}
        back
      />

      <div className="space-y-6">
        <div className="space-y-8 rounded-surface border border-border bg-surface p-6">
          <section className="space-y-5">
            <Title
              title={t("apiKey.metadataTitle")}
              description={t("apiKey.metadataDescription")}
            />
            <Input
              id="input-api-key-name"
              label={t("apiKey.keyName")}
              placeholder={t("apiKey.namePlaceholder")}
              value={apiKeyName}
              onChange={(event) => setApiKeyName(event.target.value)}
            />
            <TextArea
              id="input-api-key-description"
              label={t("apiKey.description")}
              placeholder={t("apiKey.descriptionPlaceholder")}
              value={apiKeyDescription}
              onChange={(val) => setApiKeyDescription(val)}
            />
          </section>

          <hr className="border-border" />

          <section className="space-y-5">
            <Title
              title={t("apiKey.scope")}
              description={t("apiKey.scopeDescription")}
            />
            <Table
              columns={columns}
              data={privateModels}
              getRowId={(model) => model.id}
              pageSize={5}
              emptyMessage={t("apiKey.noPrivateModels")}
            />
          </section>

          <hr className="border-border" />

          <section className="space-y-5">
            <Title
              title={t("apiKey.python")}
              description={t("apiKey.pythonDescription")}
            />
            <div className="relative overflow-hidden rounded-surface border border-terminal-border bg-terminal">
              <pre className="custom-scrollbar overflow-x-auto p-4 font-mono text-style-code-sm text-color-terminal-foreground">
                <span className="text-color-syntax-keyword">import</span>{" "}
                <span className="text-color-syntax-type">requests</span>
                {"\n\n"}
                <span className="text-color-syntax-property">
                  API_URL
                </span> ={" "}
                <span className="text-color-syntax-string">
                  "your_api_endpoint_url"
                </span>
                {"\n"}
                <span className="text-color-syntax-property">
                  API_KEY
                </span> ={" "}
                <span className="text-color-syntax-string">
                  "your_api_key_here"
                </span>
                {"\n\n"}
                <span className="text-color-syntax-variable">
                  headers
                </span> = {"{\n"}
                {"    "}
                <span className="text-color-syntax-string">
                  "X-API-Key"
                </span>:{" "}
                <span className="text-color-syntax-property">API_KEY</span>,
                {"\n"}
                {"    "}
                <span className="text-color-syntax-string">"Content-Type"</span>
                :{" "}
                <span className="text-color-syntax-string">
                  "application/json"
                </span>
                {"\n"}
                {"}\n\n"}
                <span className="text-color-syntax-variable">
                  payload
                </span> = {"{\n"}
                {"    "}
                <span className="text-color-syntax-string">
                  "features"
                </span>: {"{\n"}
                {"        "}
                <span className="text-color-syntax-string">
                  "Src Port"
                </span>: <span className="text-color-syntax-number">443</span>,
                {"\n"}
                {"        "}
                <span className="text-color-syntax-comment">
                  # Add other features...
                </span>
                {"\n"}
                {"    }\n"}
                {"}\n\n"}
                <span className="text-color-syntax-variable">
                  response
                </span> ={" "}
                <span className="text-color-syntax-variable">requests</span>.
                <span className="text-color-syntax-function">post</span>(
                <span className="text-color-syntax-property">API_URL</span>,{" "}
                <span className="text-color-syntax-variable">json</span>=
                <span className="text-color-syntax-variable">payload</span>,{" "}
                <span className="text-color-syntax-variable">headers</span>=
                <span className="text-color-syntax-variable">headers</span>)
                {"\n"}
                <span className="text-color-syntax-function">print</span>(
                <span className="text-color-syntax-variable">response</span>.
                <span className="text-color-syntax-function">json</span>())
              </pre>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(
                    `import requests\n\nAPI_URL = "http://localhost:5000/predict"\nAPI_KEY = "your_api_key_here"\n\nheaders = {\n    "X-API-Key": API_KEY,\n    "Content-Type": "application/json"\n}\n\npayload = {\n    "features": {\n        "Src Port": 443,\n        # Add other features...\n    }\n}\n\nresponse = requests.post(API_URL, json=payload, headers=headers)\nprint(response.json())`,
                  );
                  toast.success(t("apiKey.codeCopied"));
                }}
                className="absolute right-3 top-3 rounded-compact bg-terminal-header p-2 text-color-terminal-muted shadow-sm ring-1 ring-terminal-border transition-colors hover:bg-terminal-border hover:text-color-terminal-foreground active:bg-terminal-muted"
                title={t("apiKey.copyCode")}
              >
                <Copy className="h-4 w-4" />
              </button>
            </div>
          </section>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Button
            type="button"
            variant="secondary"
            fullWidth
            disabled={saving}
            onClick={() => navigate("/dashboard/api-keys")}
          >
            {t("apiKey.cancel")}
          </Button>
          <Button
            type="button"
            fullWidth
            loading={saving}
            onClick={handleSaveAPIKey}
          >
            {keyId ? t("apiKey.save") : t("apiKey.createTitle")}
          </Button>
        </div>
        <div className="h-0.5 shrink-0" aria-hidden="true" />
      </div>

      {createdApiKey && (
        <ApiKeyDialog
          title={t("apiKey.createdTitle")}
          description={t("apiKey.createdDescription")}
          apiKey={createdApiKey.api_key}
          onClose={handleDone}
          onCopy={handleCopyCreatedKey}
        />
      )}
    </div>
  );
}
