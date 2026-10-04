import { ApiModal } from "@/features/api-tokens/components/ApiModal";
import { useApiTokens } from "@/features/api-tokens/hooks/useApiTokens";
import type { APIKeyRecord } from "@/features/api-tokens/types";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { DataTable } from "@/shared/components/DataTable";
import { PageHeader } from "@/shared/components/PageHeader";
import { formatDateTime } from "@/shared/i18n/formatters";
import type { ColumnDef } from "@tanstack/react-table";
import { Edit3, KeyRound, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export default function DeveloperSettingPage() {
  const { t, i18n } = useTranslation("settings");
  const navigate = useNavigate();
  const { data: modelsData } = useModelProjects();
  const models = modelsData?.models ?? [];
  const modelIdToName = Object.fromEntries(models.map((m) => [m.id, m.name]));

  const {
    apiKeys,
    loading,
    createdApiKey,
    setCreatedApiKey,
    handleDeleteAPIKey,
    handleRegenerateAPIKey,
    handleCopyCreatedKey,
  } = useApiTokens();

  const handleDone = () => setCreatedApiKey(null);
  const [pendingAction, setPendingAction] = useState<{
    kind: "regenerate" | "delete";
    key: APIKeyRecord;
  } | null>(null);

  const columns: ColumnDef<APIKeyRecord>[] = [
    {
      id: "index",
      header: "#",
      enableSorting: false,
      cell: ({ row }) => (
        <span className="text-color-muted-foreground">{row.index + 1}</span>
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
              variant="ghost"
              aria-label={t("apiKey.edit")}
              title={t("apiKey.edit")}
              icon={<Edit3 className="h-4 w-4" />}
              onClick={() => navigate(`/dashboard/api-tokens/${record.id}`)}
            />
            <Button
              size="icon"
              variant="ghost"
              aria-label={t("apiKey.regenerate")}
              title={t("apiKey.regenerate")}
              icon={<RefreshCw className="h-4 w-4" />}
              onClick={() =>
                setPendingAction({ kind: "regenerate", key: record })
              }
            />
            <Button
              size="icon"
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
      <PageHeader
        title={t("apiKey.developerTitle")}
        actions={
          <Button
            id="btn-create-api-key"
            size="md"
            icon={<KeyRound className="h-4 w-4" />}
            onClick={() => navigate("/dashboard/api-tokens/new")}
          >
            {t("apiKey.createTitle")}
          </Button>
        }
      />

      <DataTable
        columns={columns}
        data={apiKeys}
        getRowId={(key) => key.id}
        loading={loading}
        pageSize={10}
        emptyMessage={t("apiKey.empty")}
      />

      {createdApiKey && (
        <ApiModal
          title={t("apiKey.regeneratedTitle")}
          description={t("apiKey.regeneratedDescription")}
          apiKey={createdApiKey.api_key}
          onClose={handleDone}
          onCopy={handleCopyCreatedKey}
        />
      )}
      <ConfirmModal
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
