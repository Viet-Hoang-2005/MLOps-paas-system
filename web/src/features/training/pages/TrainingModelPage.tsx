import { formatDateTime } from "@/shared/i18n/formatters";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Eye, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { listModelProjects } from "@/shared/api/catalogApi";
import {
  deleteTrainingJob,
  listTrainingJobs,
  retryTrainingJob,
} from "@/features/training/api/trainingApi";
import { Select, type SelectOption } from "@/shared/components/Select";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import { getTrainingStartError } from "@/features/training/api/quotaErrors";
import type { TrainingJob, TrainingJobStatus } from "@/features/training/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { Table } from "@/shared/components/Table";
import { toast } from "@/shared/lib/toastStore";

const ACTIVE_STATUSES: TrainingJobStatus[] = [
  "pending",
  "queued",
  "uploading",
  "running",
  "cancelling",
];

export default function TrainingModelPage() {
  const { t, i18n } = useTranslation("training");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [projectFilter, setProjectFilter] = useState("all");
  const { data: projects } = useQuery({
    queryKey: ["training", "projects"],
    queryFn: listModelProjects,
  });
  const [statusFilter, setStatusFilter] = useState("all");
  const [jobToDelete, setJobToDelete] = useState<TrainingJob | null>(null);
  const [jobToRetry, setJobToRetry] = useState<TrainingJob | null>(null);
  const retryKeys = useRef(new Map<string, string>());
  const pendingDeletionIds = useRef<Set<string>>(new Set());

  const {
    data,
    error: jobsError,
    isError,
    isFetching,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: trainingQueryKeys.jobs(),
    queryFn: () => listTrainingJobs(),
    refetchInterval: (query) => {
      const jobs = query.state.data?.training_jobs ?? [];
      return jobs.some(
        (job) =>
          (job.deletion_pending && !job.deletion_error) ||
          job.observation_status === "cleanup_pending" ||
          ACTIVE_STATUSES.includes(job.status),
      )
        ? 4000
        : false;
    },
  });

  const allTrainingJobs = useMemo(
    () => data?.training_jobs ?? [],
    [data?.training_jobs],
  );

  const projectOptions = useMemo<SelectOption[]>(() => {
    const options: SelectOption[] = [
      { value: "all", label: t("studio.allProjects") },
      { value: "unassigned", label: t("studio.unassigned") },
    ];
    if (projects?.models) {
      for (const project of projects.models) {
        options.push({ value: project.id, label: project.name });
      }
    }
    return options;
  }, [projects, t]);

  const statusOptions = useMemo<SelectOption[]>(
    () => [
      { value: "all", label: t("statusFilter.all") },
      { value: "editing", label: t("detail.statuses.editing", "Editing") },
      { value: "running", label: t("detail.statuses.running", "Running") },
      { value: "uploading", label: t("detail.statuses.uploading", "Uploading") },
      { value: "cancelling", label: t("detail.statuses.cancelling", "Cancelling") },
      { value: "completed", label: t("detail.statuses.completed", "Completed") },
      { value: "failed", label: t("detail.statuses.failed", "Failed") },
      { value: "cancelled", label: t("detail.statuses.cancelled", "Cancelled") },
      { value: "pending", label: t("detail.statuses.pending", "Pending") },
      { value: "queued", label: t("detail.statuses.queued", "Queued") },
    ],
    [t],
  );

  const trainingJobs = useMemo(
    () =>
      allTrainingJobs.filter((job) => {
        if (projectFilter === "unassigned") {
          if (job.project_id) return false;
        } else if (projectFilter !== "all") {
          if (job.project_id !== projectFilter) return false;
        }

        if (statusFilter !== "all") {
          if (job.status !== statusFilter) return false;
        }

        return true;
      }),
    [allTrainingJobs, projectFilter, statusFilter],
  );

  useEffect(() => {
    if (!pendingDeletionIds.current.size) return;
    const visibleIds = new Set(allTrainingJobs.map((job) => job.id));
    const deletedIds = [...pendingDeletionIds.current].filter(
      (id) => !visibleIds.has(id),
    );
    if (!deletedIds.length) return;
    deletedIds.forEach((id) => pendingDeletionIds.current.delete(id));
    toast.success(t("delete.completed"));
  }, [allTrainingJobs, t]);

  useEffect(() => {
    const failedDeletion = allTrainingJobs.find(
      (job) =>
        pendingDeletionIds.current.has(job.id) && Boolean(job.deletion_error),
    );
    if (!failedDeletion) return;
    pendingDeletionIds.current.delete(failedDeletion.id);
    toast.error(failedDeletion.deletion_error);
  }, [allTrainingJobs]);

  const deleteMutation = useMutation({
    mutationFn: (job: TrainingJob) => deleteTrainingJob(job.id),
    onSuccess: (request, job) => {
      pendingDeletionIds.current.add(job.id);
      queryClient.setQueryData(
        trainingQueryKeys.jobs(),
        (current: { training_jobs: TrainingJob[] } | undefined) => ({
          training_jobs: (current?.training_jobs ?? []).map((item) =>
            item.id === job.id
              ? {
                  ...item,
                  status: request.status,
                  deletion_pending: true,
                  deletion_requested_at: request.deletion_requested_at,
                  deletion_error: request.deletion_error,
                }
              : item,
          ),
        }),
      );
      setJobToDelete(null);
      toast.warning(t("delete.requested"));
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, t("delete.failed")));
    },
  });

  const retryMutation = useMutation({
    mutationFn: (job: TrainingJob) => {
      const key = retryKeys.current.get(job.id) ?? crypto.randomUUID();
      retryKeys.current.set(job.id, key);
      return retryTrainingJob(job.id, key);
    },
    onSuccess: (newJob, sourceJob) => {
      setJobToRetry(null);
      toast.success(t("studio.draftCreated"));
      void queryClient.invalidateQueries({
        queryKey: trainingQueryKeys.jobs(),
      });
      navigate(
        `/dashboard/training/${newJob.id}/workspace${
          sourceJob.project_id ? `?project=${sourceJob.project_id}` : ""
        }`,
      );
    },
    onError: (error) => {
      toast.error(getTrainingStartError(error, t, i18n.language));
    },
  });

  const columns = useMemo<ColumnDef<TrainingJob>[]>(
    () => [
      {
        accessorKey: "id",
        header: t("table.jobId", "Training job ID"),
        cell: ({ row }) => (
          <button
            type="button"
            className="break-all text-left font-medium hover:text-color-primary focus:outline-none"
            onClick={() => navigate(`/dashboard/training/${row.original.id}/workspace`)}
          >
            {row.original.id}
          </button>
        ),
      },
      {
        accessorKey: "created_at",
        header: t("table.createAt", "Create at"),
        cell: ({ row }) => (
          <span className="text-left font-medium">
            {row.original.created_at
              ? formatDateTime(row.original.created_at, i18n.language)
              : "—"}
          </span>
        ),
      },
      {
        accessorKey: "project_id",
        header: t("studio.project", "Model Project"),
        cell: ({ row }) =>
          projects?.models.find((project) => project.id === row.original.project_id)?.name ??
          t("studio.unassigned", "Unassigned"),
      },
      {
        accessorKey: "status",
        header: t("table.status", "Training status"),
        cell: ({ row }) => {
          const job = row.original;
          if (job.deletion_pending) {
            return <Badge variant="warning">{t("table.deleting", "Deleting…")}</Badge>;
          }
          const status = job.status;
          const variant =
            status === "completed"
              ? "success"
              : status === "running" || status === "uploading"
                ? "primary"
                : status === "failed"
                  ? "danger"
                  : status === "cancelling" || status === "cancelled"
                    ? "warning"
                    : "neutral";
          return (
            <Badge variant={variant}>
              {t(`detail.statuses.${status}`, status)}
            </Badge>
          );
        },
      },
      {
        accessorKey: "started_at",
        header: t("table.trainingAt", "Training at"),
        cell: ({ row }) => (
          <span className="text-left font-medium">
            {row.original.started_at
              ? formatDateTime(row.original.started_at, i18n.language)
              : "—"}
          </span>
        ),
      },
      {
        id: "actions",
        header: t("table.actions", "Action"),
        enableSorting: false,
        cell: ({ row }) => {
          const job = row.original;
          const deleting =
            (job.deletion_pending && !job.deletion_error) ||
            pendingDeletionIds.current.has(job.id);
          return (
            <div className="flex items-center gap-2">
              <Button
                size="icon"
                variant="ghost"
                aria-label={t("table.view", "View")}
                title={t("table.view", "View")}
                icon={<Eye className="h-4 w-4" />}
                disabled={deleting}
                onClick={() =>
                  navigate(`/dashboard/training/${job.id}/workspace`)
                }
              />
              <Button
                size="icon"
                variant="ghost"
                aria-label={t("retryJob", "Retry job")}
                title={t("retryJob", "Retry job")}
                icon={<RotateCcw className="h-4 w-4" />}
                disabled={deleting || retryMutation.isPending}
                onClick={() => setJobToRetry(job)}
              />
              <Button
                size="icon"
                variant="ghost"
                aria-label={t("table.delete", "Delete")}
                title={t("table.delete", "Delete")}
                icon={<Trash2 className="h-4 w-4" />}
                className="text-color-danger hover:text-color-danger-hover active:text-color-danger-active"
                disabled={deleting}
                onClick={() => setJobToDelete(job)}
              />
            </div>
          );
        },
      },
    ],
    [navigate, retryMutation.isPending, t, i18n.language, projects],
  );

  return (
    <section className="flex w-full flex-1 flex-col space-y-6">
      <PageHeader title={t("title")} />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-full sm:w-60">
            <Select
              className="h-10 text-style-body"
              value={projectFilter}
              onChange={(val) => setProjectFilter(val)}
              options={projectOptions}
              aria-label={t("studio.project")}
            />
          </div>
          <div className="w-full sm:w-60">
            <Select
              className="h-10 text-style-body"
              value={statusFilter}
              onChange={(val) => setStatusFilter(val)}
              options={statusOptions}
              placeholder={t("statusFilter.placeholder")}
              aria-label={t("statusFilter.label")}
            />
          </div>
        </div>
        <Button
          size="md"
          icon={<Plus className="h-4 w-4" />}
          onClick={() =>
            navigate(
              `/dashboard/training/new${
                projectFilter && projectFilter !== "all" && projectFilter !== "unassigned"
                  ? `?project=${projectFilter}`
                  : ""
              }`,
            )
          }
        >
          {t("newJob")}
        </Button>
      </div>

      {isError && (
        <Callout
          variant="danger"
          role="alert"
          description={`${data ? `${t("staleData")} ` : ""}${getApiErrorMessage(jobsError, t("checkApi"))}`}
          action={
            <Button
              size="sm"
              variant="secondary"
              loading={isFetching}
              onClick={() => void refetch()}
            >
              {t("retryLoad")}
            </Button>
          }
        />
      )}
      {!(isError && !data) && (
        <Table
          data={trainingJobs}
          columns={columns}
          getRowId={(job) => job.id}
          loading={isLoading}
          emptyMessage={t("table.empty")}
        />
      )}

      <ConfirmDialog
        open={Boolean(jobToDelete)}
        title={t("delete.title")}
        description={t("delete.description", { job: jobToDelete?.id ?? "" })}
        confirmText={t("delete.confirm")}
        tone="danger"
        loading={deleteMutation.isPending}
        onCancel={() => setJobToDelete(null)}
        onConfirm={() => {
          if (jobToDelete) deleteMutation.mutate(jobToDelete);
        }}
      />
      <ConfirmDialog
        open={Boolean(jobToRetry)}
        title={t("retryTitle")}
        description={t("retryDescription", { job: jobToRetry?.id ?? "" })}
        confirmText={t("retryJob")}
        tone="default"
        loading={retryMutation.isPending}
        onCancel={() => setJobToRetry(null)}
        onConfirm={() => {
          if (jobToRetry) retryMutation.mutate(jobToRetry);
        }}
      />
    </section>
  );
}
