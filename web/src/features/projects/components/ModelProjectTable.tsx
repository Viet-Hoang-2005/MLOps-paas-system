import { EditMetadataDialog } from "@/features/projects/components/EditMetadataDialog";
import { catalogQueryKeys } from "@/features/projects/queryKeys";
import type { ModelProject } from "@/features/projects/types";
import {
  deleteModelProject,
  updateModelProject,
} from "@/shared/api/catalogApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { Table } from "@/shared/components/Table";
import { formatDateTime } from "@/shared/i18n/formatters";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { PenLine, Settings2, Trash } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export interface ModelProjectTableProps {
  data: ModelProject[];
  loading?: boolean;
  emptyMessage?: string;
  onRefresh?: () => Promise<unknown> | void;
}

export function ModelProjectTable({
  data,
  loading = false,
  emptyMessage,
  onRefresh,
}: ModelProjectTableProps) {
  const { t, i18n } = useTranslation("projects");
  const navigate = useNavigate();
  const client = useQueryClient();
  const [editingProject, setEditingProject] = useState<ModelProject | null>(
    null,
  );
  const [deletingProject, setDeletingProject] = useState<ModelProject | null>(
    null,
  );

  const update = useMutation({
    mutationFn: async ({
      id,
      payload,
    }: {
      id: string;
      payload: {
        name: string;
        description: string;
        access_mode: "private" | "public";
      };
    }) => updateModelProject(id, payload),
    onSuccess: async () => {
      setEditingProject(null);
      await onRefresh?.();
      await client.invalidateQueries({ queryKey: catalogQueryKeys.projects() });
    },
  });

  const remove = useMutation({
    mutationFn: async (id: string) => deleteModelProject(id),
    onSuccess: async () => {
      setDeletingProject(null);
      await onRefresh?.();
      await client.invalidateQueries({ queryKey: catalogQueryKeys.projects() });
    },
  });

  const columns = useMemo<ColumnDef<ModelProject>[]>(
    () => [
      {
        accessorKey: "name",
        header: t("workflow.name"),
        cell: ({ row }) => (
          <button
            type="button"
            className="text-color-primary hover:underline"
            onClick={() =>
              navigate(`/dashboard/projects/${row.original.id}/overview`)
            }
          >
            {row.original.name}
          </button>
        ),
      },
      {
        accessorKey: "description",
        header: t("workflow.description"),
        cell: ({ row }) => (
          <p
            className="max-w-70 md:max-w-sm lg:max-w-md whitespace-pre-line wrap-break-word text-color-muted-foreground"
            title={row.original.description || undefined}
          >
            {row.original.description || "—"}
          </p>
        ),
      },
      {
        accessorKey: "flavor",
        header: t("flavor"),
        cell: ({ row }) => (
          <span className="whitespace-nowrap">
            {row.original.flavor || "—"}
          </span>
        ),
      },
      {
        accessorKey: "lifecycle_status",
        header: t("workflow.status"),
        cell: ({ row }) => (
          <Badge>
            {t(
              `workflow.${row.original.deletion_state !== "active" ? row.original.deletion_state : (row.original.lifecycle_status ?? "preview")}`,
            )}
          </Badge>
        ),
      },
      {
        accessorKey: "updated_at",
        header: t("updated"),
        cell: ({ row }) => (
          <span className="whitespace-nowrap">
            {formatDateTime(row.original.updated_at, i18n.language)}
          </span>
        ),
      },
      {
        id: "actions",
        header: t("workflow.actions"),
        cell: ({ row }) => (
          <div className="flex items-center gap-1 whitespace-nowrap">
            <Button
              size="icon"
              variant="secondary"
              border={false}
              icon={<PenLine className="h-4 w-4" />}
              onClick={() => setEditingProject(row.original)}
              aria-label={t("workflow.editMetadata")}
              title={t("workflow.editMetadata")}
            />
            <Button
              size="icon"
              variant="secondary"
              border={false}
              icon={<Settings2 className="h-4 w-4" />}
              onClick={() =>
                navigate(`/dashboard/projects/${row.original.id}/edit`)
              }
              aria-label={t("workflow.editPreview")}
              title={t("workflow.editPreview")}
            />
            <Button
              size="icon"
              variant="danger"
              border={false}
              icon={<Trash className="h-4 w-4" />}
              onClick={() => setDeletingProject(row.original)}
              aria-label={t("workflow.delete")}
              title={t("workflow.delete")}
            />
          </div>
        ),
      },
    ],
    [t, i18n.language, navigate],
  );

  return (
    <>
      <Table
        columns={columns}
        data={data}
        loading={loading}
        emptyMessage={emptyMessage}
      />
      {editingProject && (
        <EditMetadataDialog
          open={Boolean(editingProject)}
          onClose={() => setEditingProject(null)}
          project={{
            name: editingProject.name,
            description: editingProject.description,
            access_mode: editingProject.access_mode,
          }}
          onSave={(payload) =>
            update.mutateAsync({ id: editingProject.id, payload })
          }
          loading={update.isPending}
          error={update.error}
        />
      )}
      <ConfirmDialog
        open={Boolean(deletingProject)}
        title={t("workflow.delete")}
        description={t("workflow.deleteHint")}
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => {
          if (deletingProject) {
            remove.mutate(deletingProject.id);
          }
        }}
        onCancel={() => setDeletingProject(null)}
      />
      {remove.isError && (
        <p role="alert">
          {getApiErrorMessage(remove.error, t("workflow.failed"))}
        </p>
      )}
    </>
  );
}
