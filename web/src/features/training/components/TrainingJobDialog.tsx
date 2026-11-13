import { useCallback, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Eye, Trash2 } from "lucide-react";
import BaseDialog from "@/shared/components/BaseDialog";
import { Table } from "@/shared/components/Table";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { formatDateTime } from "@/shared/i18n/formatters";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import { listWorkspaceJobs } from "@/features/training/api/jobWorkspaceApi";
import { deleteTrainingJob } from "@/features/training/api/trainingApi";
import type { TrainingJob } from "@/features/training/types";

export function TrainingJobDialog({
  workspaceId,
  currentJobId,
  onClose,
}: {
  workspaceId: string;
  currentJobId?: string;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation("training");
  const navigate = useNavigate();
  const client = useQueryClient();
  const [page, setPage] = useState(1);
  const [deleting, setDeleting] = useState<TrainingJob | null>(null);
  const [busy, setBusy] = useState(false);
  const query = useQuery({
    queryKey: ["training", "workspace-jobs", workspaceId, page],
    queryFn: () => listWorkspaceJobs(workspaceId, page),
    refetchInterval: 4000,
  });
  const open = useCallback(
    (id?: string) => {
      navigate(
        `/dashboard/training/workspaces/${workspaceId}${id ? `/jobs/${id}` : ""}`,
      );
      onClose();
    },
    [navigate, workspaceId, onClose],
  );
  const columns = useMemo<ColumnDef<TrainingJob>[]>(
    () => [
      {
        accessorKey: "id",
        header: t("workspaceHistory.jobId"),
        cell: ({ row }) => (
          <Button variant="ghost" onClick={() => open(row.original.id)}>
            {row.original.id}
          </Button>
        ),
      },
      {
        accessorKey: "project_name",
        header: t("workspaceHistory.project"),
        cell: ({ row }) => row.original.project_name || t("studio.unassigned"),
      },
      {
        accessorKey: "status",
        header: t("workspaceHistory.status"),
        cell: ({ row }) => t(`detail.statuses.${row.original.status}`),
      },
      {
        id: "started",
        header: t("workspaceHistory.trainingAt"),
        cell: ({ row }) =>
          row.original.runtime_started_at || row.original.started_at
            ? formatDateTime(
                row.original.runtime_started_at || row.original.started_at!,
                i18n.language,
              )
            : "—",
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
              disabled={row.original.deletion_pending}
              aria-label={t("workspaceHistory.delete")}
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
    <BaseDialog
      title={t("workspaceHistory.title")}
      onClose={onClose}
      className="w-[min(96vw,80rem)]"
    >
      <div className="space-y-4">
        <Button
          variant="secondary"
          disabled={!currentJobId}
          onClick={() => open()}
        >
          {t("workspaceHistory.backToCurrent")}
        </Button>
        {query.isError ? (
          <div role="alert">
            <p>{getApiErrorMessage(query.error, t("studio.failed"))}</p>
            <Button onClick={() => void query.refetch()}>
              {t("studio.reload")}
            </Button>
          </div>
        ) : (
          <Table
            data={query.data?.training_jobs ?? []}
            columns={columns}
            getRowId={(row) => row.id}
            loading={query.isLoading}
            emptyMessage={t("workspaceHistory.empty")}
          />
        )}
        <div className="flex items-center justify-end gap-3">
          <Button disabled={page === 1} onClick={() => setPage(page - 1)}>
            {t("workspaceHistory.previous")}
          </Button>
          <span>{page}</span>
          <Button
            disabled={
              !query.data || page * query.data.page_size >= query.data.count
            }
            onClick={() => setPage(page + 1)}
          >
            {t("workspaceHistory.next")}
          </Button>
        </div>
      </div>
      <ConfirmDialog
        open={Boolean(deleting)}
        title={t("workspaceHistory.delete")}
        description={t("workspaceHistory.deleteJobDescription")}
        tone="danger"
        loading={busy}
        onCancel={() => setDeleting(null)}
        onConfirm={async () => {
          if (!deleting) return;
          setBusy(true);
          try {
            await deleteTrainingJob(deleting.id);
            await client.invalidateQueries({ queryKey: ["training"] });
            if (deleting.id === currentJobId) open();
            setDeleting(null);
          } catch (error) {
            toast.error(getApiErrorMessage(error, t("studio.failed")));
          } finally {
            setBusy(false);
          }
        }}
      />
    </BaseDialog>
  );
}
