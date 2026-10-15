import { ApiKeyDialog } from "@/features/api-keys/components/ApiKeyDialog";
import { useApiTokens as useApiKeys } from "@/features/api-keys/hooks/useApiTokens";
import type { APIKeyRecord } from "@/features/api-keys/types";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { Select, type SelectOption } from "@/shared/components/Select";
import { Table } from "@/shared/components/Table";
import { formatDateTime } from "@/shared/i18n/formatters";
import type { ColumnDef } from "@tanstack/react-table";
import { Edit3, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export default function DeveloperSettingPage() {
  const { t, i18n } = useTranslation("settings");
  const navigate = useNavigate();
  const { data: modelsData } = useModelProjects();
  const models = useMemo(() => modelsData?.models ?? [], [modelsData?.models]);
  const modelIdToName = useMemo(
    () => Object.fromEntries(models.map((m) => [m.id, m.name])),
    [models],
  );

  const {
    apiKeys,
    loading,
    createdApiKey,
    setCreatedApiKey,
    handleDeleteAPIKey,
    handleRegenerateAPIKey,
    handleCopyCreatedKey,
  } = useApiKeys();

  const handleDone = () => setCreatedApiKey(null);
  const [pendingAction, setPendingAction] = useState<{
    kind: "regenerate" | "delete";
    key: APIKeyRecord;
  } | null>(null);

  const [scopeFilter, setScopeFilter] = useState("all");

  const scopeOptions = useMemo<SelectOption[]>(() => {
    const options: SelectOption[] = [
      { value: "all", label: t("apiKey.allScopes") },
      { value: "all_models", label: t("apiKey.allModels") },
    ];
    const seenIds = new Set<string>();
    for (const model of models) {
      seenIds.add(model.id);
      options.push({
        value: model.id,
        label: model.name,
      });
    }
    for (const key of apiKeys) {
      for (const id of key.allowed_models || []) {
        if (!seenIds.has(id)) {
          seenIds.add(id);
          options.push({
            value: id,
            label: modelIdToName[id] || t("apiKey.unknownModel", { id }),
          });
        }
      }
    }
    return options;
  }, [apiKeys, modelIdToName, models, t]);

  const filteredApiKeys = useMemo(() => {
    if (scopeFilter === "all") return apiKeys;
    if (scopeFilter === "all_models") {
      return apiKeys.filter((key) => key.scope === "all");
    }
    return apiKeys.filter((key) => key.allowed_models?.includes(scopeFilter));
  }, [apiKeys, scopeFilter]);

  const columns: ColumnDef<APIKeyRecord>[] = [
    {
      accessorKey: "name",
      header: t("apiKey.name"),
      cell: ({ row }) => (
        <button
          type="button"
          className="text-left text-color-primary hover:underline"
          onClick={() => navigate(`/dashboard/api-keys/${row.original.id}`)}
        >
          {row.original.name}
        </button>
      ),
    },
    {
      accessorKey: "description",
      header: t("apiKey.description"),
      cell: ({ row }) => (
        <span className="line-clamp-2 max-w-sm text-style-body text-color-muted-foreground">
          {row.original.description || t("apiKey.noDescription")}
        </span>
      ),
    },
    {
      id: "models",
      header: t("apiKey.modelScope"),
      enableSorting: false,
      cell: ({ row }) => {
        const record = row.original;
        const scope = record.scope;
        if (scope === "all") {
          return <Badge variant="primary">{t("apiKey.allModels")}</Badge>;
        }
        if (!record.allowed_models || record.allowed_models.length === 0) {
          return <Badge variant="danger">{t("apiKey.noModels")}</Badge>;
        }
        return (
          <div className="flex max-w-xs flex-wrap gap-1">
            {record.allowed_models.map((id) => (
              <Badge key={id}>
                {modelIdToName[id] || t("apiKey.unknownModel", { id })}
              </Badge>
            ))}
          </div>
        );
      },
    },
    {
      accessorKey: "created_at",
      header: t("apiKey.created"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap text-color-muted-foreground">
          {formatDateTime(row.original.created_at, i18n.language)}
        </span>
      ),
    },
    {
      id: "actions",
      header: t("apiKey.actions"),
      enableSorting: false,
      cell: ({ row }) => {
        const record = row.original;
        return (
          <div className="flex items-center gap-1">
            <Button
              size="icon"
              border={false}
              aria-label={t("apiKey.edit")}
              title={t("apiKey.edit")}
              icon={<Edit3 className="h-4 w-4" />}
              onClick={() => navigate(`/dashboard/api-keys/${record.id}`)}
            />
            <Button
              size="icon"
              border={false}
              aria-label={t("apiKey.regenerate")}
              title={t("apiKey.regenerate")}
              icon={<RefreshCw className="h-4 w-4" />}
              onClick={() =>
                setPendingAction({ kind: "regenerate", key: record })
              }
            />
            <Button
              size="icon"
              border={false}
              aria-label={t("apiKey.delete")}
              title={t("apiKey.delete")}
              variant="danger-outline"
              icon={<Trash2 className="h-4 w-4" />}
              onClick={() => setPendingAction({ kind: "delete", key: record })}
            />
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title={t("apiKey.developerTitle")} />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="w-full sm:w-64">
          <Select
            className="h-10 text-style-body"
            value={scopeFilter}
            onChange={setScopeFilter}
            options={scopeOptions}
            placeholder={t("apiKey.filterByScope")}
          />
        </div>
        <Button
          id="btn-create-api-key"
          size="md"
          icon={<Plus className="h-4 w-4" />}
          onClick={() => navigate("/dashboard/api-keys/new")}
        >
          {t("apiKey.createTitle")}
        </Button>
      </div>

      <Table
        columns={columns}
        data={filteredApiKeys}
        getRowId={(key) => key.id}
        loading={loading}
        pageSize={10}
        emptyMessage={
          scopeFilter !== "all"
            ? t("apiKey.noMatchingKeys")
            : t("apiKey.empty")
        }
      />

      {createdApiKey && (
        <ApiKeyDialog
          title={t("apiKey.regeneratedTitle")}
          description={t("apiKey.regeneratedDescription")}
          apiKey={createdApiKey.api_key}
          onClose={handleDone}
          onCopy={handleCopyCreatedKey}
        />
      )}
      <ConfirmDialog
        open={Boolean(pendingAction)}
        title={
          pendingAction?.kind === "delete"
            ? t("apiKey.delete")
            : t("apiKey.regenerate")
        }
        description={
          pendingAction?.kind === "delete"
            ? t("apiKey.deleteDescription", { name: pendingAction.key.name })
            : t("apiKey.regenerateDescription", {
                name: pendingAction?.key.name,
              })
        }
        confirmText={
          pendingAction?.kind === "delete"
            ? t("apiKey.deleteKey")
            : t("apiKey.regenerateKey")
        }
        tone={pendingAction?.kind === "delete" ? "danger" : "default"}
        onConfirm={() => {
          if (pendingAction?.kind === "delete")
            void handleDeleteAPIKey(pendingAction.key);
          if (pendingAction?.kind === "regenerate")
            void handleRegenerateAPIKey(pendingAction.key);
          setPendingAction(null);
        }}
        onCancel={() => setPendingAction(null)}
      />
    </div>
  );
}
