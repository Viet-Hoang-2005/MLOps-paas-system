import { useCallback, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Eye, Trash2, ArrowLeft } from "lucide-react";
import BaseDialog from "@/shared/components/BaseDialog";
import { Table } from "@/shared/components/Table";
import { Button } from "@/shared/components/Button";
import { Badge } from "@/shared/components/Badge";
import { Select } from "@/shared/components/Select";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { formatDateTime } from "@/shared/i18n/formatters";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/lib/toastStore";
import { listWorkspaceJobs } from "@/features/training/api/jobWorkspaceApi";
import { deleteTrainingJob } from "@/features/training/api/trainingApi";
import type { TrainingJob, TrainingJobStatus } from "@/features/training/types";

const JOB_STATUSES: TrainingJobStatus[] = [
  "pending",
  "queued",
  "uploading",
  "running",
  "completed",
  "failed",
  "cancelling",
  "cancelled",
];

const getJobStatusVariant = (
  status: TrainingJobStatus,
): "success" | "primary" | "info" | "warning" | "danger" | "neutral" => {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
      return "danger";
    case "running":
    case "uploading":
      return "primary";
    case "cancelling":
    case "cancelled":
      return "warning";
    case "pending":
    case "queued":
      return "info";
    default:
      return "neutral";
  }
};

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
  const [statusFilter, setStatusFilter] = useState("all");
  const [deleting, setDeleting] = useState<TrainingJob | null>(null);
  const [busy, setBusy] = useState(false);
  const query = useQuery({
    queryKey: ["training", "workspace-jobs", workspaceId],
    queryFn: () => listWorkspaceJobs(workspaceId),
    refetchInterval: 4000,
  });

  const handleStatusFilterChange = (value: string) => {
    setStatusFilter(value);
  };

  const filteredJobs = useMemo(() => {
    const jobs = query.data?.training_jobs ?? [];
    if (statusFilter === "all") return jobs;
    return jobs.filter((job) => job.status === statusFilter);
  }, [query.data?.training_jobs, statusFilter]);

  const open = useCallback(
    (id?: string) => {
      navigate(
        `/dashboard/training/workspaces/${workspaceId}${id ? `/job/${id}` : ""}`,
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
          <button
            type="button"
            className="text-color-primary hover:underline"
            onClick={() => open(row.original.id)}
          >
            {row.original.id}
          </button>
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
        cell: ({ row }) => (
          <Badge variant={getJobStatusVariant(row.original.status)}>
            {t(`detail.statuses.${row.original.status}`)}
          </Badge>
        ),
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
              size="icon"
              variant="secondary"
              border={false}
              aria-label={t("workspaceHistory.view")}
              onClick={() => open(row.original.id)}
            >
              <Eye className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="secondary"
              border={false}
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
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Button
            variant="primary"
            disabled={!currentJobId}
            icon={<ArrowLeft className="h-4 w-4" />}
            onClick={() => open()}
          >
            {t("workspaceHistory.currentWorkspace")}
          </Button>
          <div className="w-full sm:w-60">
            <Select
              aria-label={t("workspaceHistory.status")}
              value={statusFilter}
              onChange={handleStatusFilterChange}
              options={[
                { value: "all", label: t("statusFilter.all") },
                ...JOB_STATUSES.map((status) => ({
                  value: status,
                  label: t(`detail.statuses.${status}`),
                })),
              ]}
            />
          </div>
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
            data={filteredJobs}
            columns={columns}
            getRowId={(row) => row.id}
            loading={query.isLoading}
            emptyMessage={t("workspaceHistory.empty")}
            pageSize={10}
          />
        )}
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
