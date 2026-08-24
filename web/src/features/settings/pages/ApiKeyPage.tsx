import { Copy } from "lucide-react";
import { useParams, useNavigate } from "react-router-dom";
import { useMemo } from "react";
import { Button } from "@/shared/components/Button";
import { Input } from "@/shared/components/Input";
import { ApiModal } from "@/features/settings/components/ApiModal";
import { useApiKeyForm } from "@/features/settings/hooks/useApiKeyForm";
import { useDeveloperSettings } from "@/features/settings/hooks/useDeveloperSettings";
import { useModelProjects } from "@/features/catalog/hooks/useModelProjects";
import { toast } from "@/shared/components/toastStore";
import type { ColumnDef } from "@tanstack/react-table";
import type { ModelProject } from "@/features/catalog/types";
import { PageHeader } from "@/shared/components/PageHeader";
import { PageBody } from "@/shared/components/PageBody";
import { DataTable } from "@/shared/components/DataTable";
import { useTranslation } from "react-i18next";

export default function ApiKeyPage() {
  const { t } = useTranslation("settings");
  const { keyId } = useParams<{ keyId?: string }>();
  const navigate = useNavigate();
  const { apiKeys } = useDeveloperSettings();

  const editingKey = useMemo(() => {
    if (!keyId) return null;
    return apiKeys.find((key) => key.id === keyId) || null;
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
    navigate("/dashboard/settings/developer");
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
        <span className="font-medium text-color-foreground">{row.original.name}</span>
      ),
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
        backLink={{
          to: "/dashboard/settings/developer",
          label: t("apiKey.back"),
        }}
      />

      <PageBody className="p-6 space-y-6">
        <div className="space-y-4">
          <Input
            id="input-api-key-name"
            label={t("apiKey.apiName")}
            placeholder={t("apiKey.namePlaceholder")}
            value={apiKeyName}
            onChange={(event) => setApiKeyName(event.target.value)}
          />
          <label
            htmlFor="input-api-key-description"
            className="flex flex-col gap-2 text-style-body-strong text-color-foreground"
          >
            {t("apiKey.description")}
            <textarea
              id="input-api-key-description"
              className="min-h-24 w-full resize-none rounded-control border border-border bg-surface px-4 py-3 text-style-body text-color-foreground outline-none transition-colors duration-200 placeholder:text-color-muted-foreground hover:border-primary focus:border-primary"
              placeholder={t("apiKey.descriptionPlaceholder")}
              value={apiKeyDescription}
              onChange={(event) => setApiKeyDescription(event.target.value)}
            />
          </label>
          <div className="flex flex-col gap-2 pt-2">
            <span className="text-style-body-strong text-color-foreground">
              {t("apiKey.scope")}
            </span>
            <div className="rounded-surface border border-border bg-surface overflow-hidden mt-1">
              <DataTable
                columns={columns}
                data={privateModels}
                getRowId={(model) => model.id}
                pageSize={5}
                emptyMessage={t("apiKey.noPrivateModels")}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2 pt-4">
            <span className="text-style-body-strong text-color-foreground">
              {t("apiKey.python")}
            </span>
            <div className="relative overflow-hidden rounded-surface border border-terminal-border bg-terminal">
              <pre className="custom-scrollbar overflow-x-auto p-4 font-mono text-style-code-sm text-color-terminal-foreground">
                <span className="text-color-syntax-keyword">import</span>{" "}
                <span className="text-color-syntax-type">requests</span>
                {"\n\n"}
                <span className="text-color-syntax-property">API_URL</span> ={" "}
                <span className="text-color-syntax-string">"your_api_endpoint_url"</span>
                {"\n"}
                <span className="text-color-syntax-property">API_KEY</span> ={" "}
                <span className="text-color-syntax-string">"your_api_key_here"</span>
                {"\n\n"}
                <span className="text-color-syntax-variable">headers</span> = {"{\n"}
                {"    "}
                <span className="text-color-syntax-string">"X-API-Key"</span>:{" "}
                <span className="text-color-syntax-property">API_KEY</span>,{"\n"}
                {"    "}
                <span className="text-color-syntax-string">"Content-Type"</span>:{" "}
                <span className="text-color-syntax-string">"application/json"</span>
                {"\n"}
                {"}\n\n"}
                <span className="text-color-syntax-variable">payload</span> = {"{\n"}
                {"    "}
                <span className="text-color-syntax-string">"features"</span>: {"{\n"}
                {"        "}
                <span className="text-color-syntax-string">"Src Port"</span>:{" "}
                <span className="text-color-syntax-number">443</span>,{"\n"}
                {"        "}
                <span className="text-color-syntax-comment"># Add other features...</span>
                {"\n"}
                {"    }\n"}
                {"}\n\n"}
                <span className="text-color-syntax-variable">response</span> ={" "}
                <span className="text-color-syntax-variable">requests</span>.
                <span className="text-color-syntax-function">post</span>(
                <span className="text-color-syntax-property">API_URL</span>,{" "}
                <span className="text-color-syntax-variable">json</span>=
                <span className="text-color-syntax-variable">payload</span>,{" "}
                <span className="text-color-syntax-variable">headers</span>=
                <span className="text-color-syntax-variable">headers</span>){"\n"}
                <span className="text-color-syntax-function">print</span>(
                <span className="text-color-syntax-variable">response</span>.
                <span className="text-color-syntax-function">json</span>())
              </pre>
              <button
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
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3 border-t border-border pt-6">
          <Button
            variant="secondary"
            onClick={() => navigate("/dashboard/settings/developer")}
          >
            {t("apiKey.cancel")}
          </Button>
          <Button loading={saving} onClick={handleSaveAPIKey}>
            {keyId ? t("apiKey.save") : t("apiKey.createTitle")}
          </Button>
        </div>
      </PageBody>

      {createdApiKey && (
        <ApiModal
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
