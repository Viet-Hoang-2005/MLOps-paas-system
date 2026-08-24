import { Edit3, KeyRound, RefreshCw, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/shared/components/Button";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { ApiModal } from "@/features/settings/components/ApiModal";
import { useDeveloperSettings } from "@/features/settings/hooks/useDeveloperSettings";
import { useModelProjects } from "@/features/catalog/hooks/useModelProjects";
import type { APIKeyRecord } from "@/features/settings/types";
import { PageBody } from "@/shared/components/PageBody";
import { DataTable } from "@/shared/components/DataTable";
import { Badge } from "@/shared/components/Badge";
import { useTranslation } from "react-i18next";

export default function DeveloperSettingPage() {
  const { t } = useTranslation("settings");
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
  } = useDeveloperSettings();

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
          {new Date(row.original.created_at).toLocaleString()}
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
              onClick={() =>
                navigate(`/dashboard/settings/developer/api-keys/${record.id}`)
              }
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
    <div className="flex w-full flex-1 flex-col space-y-6">
      <PageBody>
        <div className="flex flex-col gap-4 border-b border-border px-6 py-6 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-style-section-title font-bold text-color-foreground">
              {t("apiKey.developerTitle")}
            </h2>
            <p className="mt-1 text-style-body text-color-muted-foreground">
              {t("apiKey.developerDescription")}
            </p>
          </div>
          <Button
            id="btn-create-api-key"
            size="md"
            icon={<KeyRound className="h-4 w-4" />}
            onClick={() =>
              navigate("/dashboard/settings/developer/api-keys/create")
            }
          >
            {t("apiKey.createTitle")}
          </Button>
        </div>

        <div className="px-6 py-6">
          <DataTable
            columns={columns}
            data={apiKeys}
            getRowId={(key) => key.id}
            loading={loading}
            pageSize={10}
            emptyMessage={t("apiKey.empty")}
          />
        </div>
      </PageBody>

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
