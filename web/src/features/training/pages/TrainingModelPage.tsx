import { useCallback, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Eye, Play, Plus, Trash2 } from "lucide-react";
import { listModelProjects } from "@/shared/api/catalogApi";
import { Button } from "@/shared/components/Button";
import { PageHeader } from "@/shared/components/PageHeader";
import { Table } from "@/shared/components/Table";
import { Select } from "@/shared/components/Select";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { formatDateTime } from "@/shared/i18n/formatters";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import {
  listTrainingWorkspaces,
  deleteTrainingWorkspace,
  type TrainingWorkspace,
} from "@/features/training/api/jobWorkspaceApi";

export default function TrainingModelPage() {
  const { t, i18n } = useTranslation("training");
  const navigate = useNavigate();
  const client = useQueryClient();
  const [project, setProject] = useState("all");
  const [status, setStatus] = useState("all");
  const [deleting, setDeleting] = useState<TrainingWorkspace | null>(null);
  const [busy, setBusy] = useState(false);
  const projects = useQuery({
    queryKey: ["training", "projects"],
    queryFn: listModelProjects,
  });
  const query = useQuery({
    queryKey: ["training", "workspaces", project],
    queryFn: () =>
      listTrainingWorkspaces(project === "all" ? undefined : project),
    refetchInterval: 4000,
  });
  const open = useCallback(
    (id: string, run = false) =>
      navigate(
        "/dashboard/training/workspaces/" + id + (run ? "?focus=terminal" : ""),
      ),
    [navigate],
  );
  const columns = useMemo<ColumnDef<TrainingWorkspace>[]>(
    () => [
      {
        accessorKey: "id",
        header: t("workspaceHistory.workspaceId"),
        cell: ({ row }) => (
          <Button variant="ghost" onClick={() => open(row.original.id)}>
            {row.original.id}
          </Button>
        ),
      },
      { accessorKey: "job_count", header: t("workspaceHistory.title") },
      {
        accessorKey: "status",
        header: t("workspaceHistory.workspaceStatus"),
        cell: ({ row }) => t("workspaceHistory.states." + row.original.status),
      },
      {
        accessorKey: "created_at",
        header: t("workspaceHistory.createdAt"),
        cell: ({ row }) =>
          formatDateTime(row.original.created_at, i18n.language),
      },
      {
        accessorKey: "updated_at",
        header: t("workspaceHistory.updatedAt"),
        cell: ({ row }) =>
          formatDateTime(row.original.updated_at, i18n.language),
      },
      {
        id: "actions",
        header: t("workspaceHistory.actions"),
        cell: ({ row }) => (
          <div className="flex gap-2">
            <Button
              variant="ghost"
              aria-label={t("workspaceHistory.view")}
              onClick={() => open(row.original.id)}
            >
              <Eye className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              disabled={row.original.status !== "ready"}
              aria-label={t("studio.run")}
              onClick={() => open(row.original.id, true)}
            >
              <Play className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              disabled={row.original.status === "deleting"}
              aria-label={t("workspaceHistory.deleteWorkspace")}
              onClick={() => setDeleting(row.original)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        ),
      },
    ],
    [t, i18n.language, open],
  );
  return (
    <section className="space-y-5">
      <PageHeader
        title={t("title")}
        actions={
          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => navigate("/dashboard/training/new")}
          >
            {t("workspaceHistory.newWorkspace")}
          </Button>
        }
      />
      <div className="flex gap-4">
        <Select
          aria-label={t("workspaceHistory.project")}
          value={project}
          onChange={setProject}
          options={[
            { value: "all", label: t("studio.allProjects") },
            { value: "unassigned", label: t("studio.unassigned") },
            ...(projects.data?.models ?? []).map((item) => ({
              value: item.id,
              label: item.name,
            })),
          ]}
        />
        <Select
          aria-label={t("workspaceHistory.workspaceStatus")}
          value={status}
          onChange={setStatus}
          options={[
            "all",
            "ready",
            "preparing",
            "running",
            "deleting",
            "delete_failed",
          ].map((value) => ({
            value,
            label: t("workspaceHistory.states." + value),
          }))}
        />
      </div>
      {query.isError ? (
        <div role="alert">
          <p>{getApiErrorMessage(query.error, t("studio.failed"))}</p>
          <Button onClick={() => void query.refetch()}>
            {t("studio.reload")}
          </Button>
        </div>
      ) : (
        <Table
          data={(query.data?.workspaces ?? []).filter(
            (row) => status === "all" || row.status === status,
          )}
          columns={columns}
          getRowId={(row) => row.id}
          loading={query.isLoading}
          emptyMessage={t("workspaceHistory.noWorkspaces")}
        />
      )}
      <ConfirmDialog
        open={Boolean(deleting)}
        title={t("workspaceHistory.deleteWorkspace")}
        description={t("workspaceHistory.deleteWorkspaceDescription", {
          count: deleting?.job_count ?? 0,
        })}
        tone="danger"
        loading={busy}
        onCancel={() => setDeleting(null)}
        onConfirm={async () => {
          if (!deleting) return;
          setBusy(true);
          try {
            await deleteTrainingWorkspace(deleting.id);
            setDeleting(null);
            await client.invalidateQueries({ queryKey: ["training"] });
          } catch (error) {
            toast.error(getApiErrorMessage(error, t("studio.failed")));
          } finally {
            setBusy(false);
          }
        }}
      />
    </section>
  );
}
