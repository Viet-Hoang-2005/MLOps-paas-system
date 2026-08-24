import { useState } from "react";
import { Bot, Edit3, Trash2, Search, Plus, Download } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/shared/components/Button";
import { Input } from "@/shared/components/Input";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { DataTable } from "@/shared/components/DataTable";
import { Badge } from "@/shared/components/Badge";
import { Placeholder } from "@/shared/components/Placeholder";
import {
  useModelProjects,
  useModelProjectMutations,
} from "@/features/catalog/hooks/useModelProjects";
import type { ModelProject } from "@/features/catalog/types";
import EditModelModal from "@/features/deploy/components/EditModelModal";
import { PageHeader } from "@/shared/components/PageHeader";
import { useTranslation } from "react-i18next";

const lifecycleBadgeVariant = {
  metadata: "neutral",
  image_ready: "primary",
  deployed: "success",
} as const;

export default function ModelManagementPage() {
  const { t, i18n } = useTranslation("deploy");
  const navigate = useNavigate();
  const { data, isLoading } = useModelProjects();
  const { deleteModelProject } = useModelProjectMutations();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedModel, setSelectedModel] = useState<ModelProject | null>(null);
  const [modelToDelete, setModelToDelete] = useState<ModelProject | null>(null);
  const [isModalVisible, setIsModalVisible] = useState(false);

  const models = data?.models ?? [];
  const filteredModels = models.filter((model) =>
    model.name.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  const columns: ColumnDef<ModelProject>[] = [
    {
      id: "index",
      header: t("columns.index"),
      enableSorting: false,
      cell: ({ row }) => (
        <span className="text-color-muted-foreground">{row.index + 1}</span>
      ),
    },
    {
      accessorKey: "name",
      header: t("columns.name"),
      cell: ({ row }) => (
        <button
          type="button"
          className="text-left font-semibold text-color-foreground hover:text-color-primary"
          onClick={() =>
            navigate(`/dashboard/management/model/${row.original.id}`)
          }
        >
          {row.original.name}
        </button>
      ),
    },
    {
      accessorKey: "description",
      header: t("columns.description"),
      cell: ({ row }) => (
        <span className="line-clamp-2 max-w-sm text-style-body text-color-muted-foreground">
          {row.original.description || t("noDescription")}
        </span>
      ),
    },
    {
      accessorKey: "flavor",
      header: t("columns.flavor"),
      cell: ({ row }) => (
        <Badge variant={"primary"}>{row.original.flavor || t("status.metadata")}</Badge>
      ),
    },
    {
      accessorKey: "access_mode",
      header: t("columns.access"),
      cell: ({ row }) => (
        <Badge
          variant={
            row.original.access_mode === "public" ? "success" : "neutral"
          }
        >
          {row.original.access_mode}
        </Badge>
      ),
    },
    {
      accessorKey: "lifecycle_status",
      header: t("columns.status"),
      cell: ({ row }) => {
        const status = row.original.lifecycle_status ?? "metadata";
        const label =
          status === "image_ready"
            ? t("status.built")
            : status === "deployed"
              ? t("status.deployed")
              : t("status.metadata");
        return <Badge variant={lifecycleBadgeVariant[status]}>{label}</Badge>;
      },
    },
    {
      accessorKey: "updated_at",
      header: t("columns.updated"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap text-color-muted-foreground">
          {new Date(row.original.updated_at).toLocaleString(i18n.language)}
        </span>
      ),
    },
    {
      id: "actions",
      header: t("columns.actions"),
      enableSorting: false,
      cell: ({ row }) => {
        const record = row.original;
        return (
          <div className="flex items-center gap-1">
            <Button
              size="icon"
              variant="ghost"
              aria-label={t("actions.downloadModel")}
              title={t("actions.downloadModel")}
              icon={<Download className="h-4 w-4" />}
              onClick={() => {
                if (record.model_uri)
                  window.open(
                    record.model_uri,
                    "_blank",
                    "noopener,noreferrer",
                  );
              }}
              disabled={!record.model_uri}
            />
            <Button
              size="icon"
              variant="ghost"
              aria-label={t("actions.editModel")}
              title={t("actions.editModel")}
              icon={<Edit3 className="h-4 w-4" />}
              onClick={() => {
                setSelectedModel(record);
                setIsModalVisible(true);
              }}
            />
            <Button
              size="icon"
              variant="ghost"
              aria-label={t("actions.deleteModel")}
              title={t("actions.deleteModel")}
              className="text-color-danger hover:text-color-danger-hover active:text-color-danger-active"
              icon={<Trash2 className="h-4 w-4" />}
              onClick={() => setModelToDelete(record)}
            />
          </div>
        );
      },
    },
  ];

  return (
    <div className="flex w-full flex-1 flex-col space-y-6">
      <PageHeader title={t("title")} />

      <div className="flex flex-1 flex-col space-y-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="w-full md:w-96">
            <Input
              placeholder={t("search")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              icon={<Search className="h-4 w-4" />}
              className="h-10! rounded-surface!"
            />
          </div>
          <Button
            size="md"
            onClick={() =>
              navigate("/dashboard/management/model/upload/metadata")
            }
          >
            <Plus className="h-4 w-4" />
            {t("upload")}
          </Button>
        </div>

        <div className="flex flex-1 flex-col">
          {isLoading ? (
            <div className="rounded-surface border border-dashed border-border py-12 text-center text-style-body text-color-muted-foreground">
              {t("loading")}
            </div>
          ) : filteredModels.length === 0 ? (
            <Placeholder
              title={t("noModels")}
              description={
                searchQuery
                  ? t("noMatch", { query: searchQuery })
                  : t("noModelsDescription")
              }
              icon={<Bot className="h-6 w-6" />}
              showModelName={false}
              action={
                !searchQuery && (
                  <Button
                    size="md"
                    onClick={() =>
                      navigate("/dashboard/management/model/upload/metadata")
                    }
                  >
                    {t("upload")}
                  </Button>
                )
              }
            />
          ) : (
            <DataTable
              columns={columns}
              data={filteredModels}
              getRowId={(model) => model.id}
              pageSize={10}
            />
          )}
        </div>
      </div>

      <EditModelModal
        key={`edit-modal-${selectedModel?.id || "none"}-${isModalVisible}`}
        model={selectedModel}
        visible={isModalVisible}
        onClose={() => {
          setIsModalVisible(false);
          setSelectedModel(null);
        }}
      />
      <ConfirmModal
        open={Boolean(modelToDelete)}
        title={t("deleteTitle")}
        description={t("deleteDescription", { name: modelToDelete?.name })}
        confirmText={t("deleteConfirm")}
        tone="danger"
        onConfirm={() => {
          if (modelToDelete) void deleteModelProject(modelToDelete.id);
          setModelToDelete(null);
        }}
        onCancel={() => setModelToDelete(null)}
      />
    </div>
  );
}
