import { formatDateTime, formatNumber } from "@/shared/i18n/formatters";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Eye, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { listModelProjects } from "@/shared/api/catalogApi";
import {
  deleteTrainingJob,
  getTrainingUsage,
  listTrainingJobs,
  retryTrainingJob,
} from "@/features/training/api/trainingApi";
import type { TrainingStatusFilter } from "@/features/training/components/TrainingJobListSections";
import { Select, type SelectOption } from "@/shared/components/Select";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import { getTrainingStartError } from "@/features/training/api/quotaErrors";
import { formatQuotaDuration } from "@/features/training/api/quotaFormatting";
import type { TrainingJob, TrainingJobStatus } from "@/features/training/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { Table } from "@/shared/components/Table";
import { formatDuration } from "@/shared/lib/formatDuration";
import { toast } from "@/shared/lib/toastStore";

const ACTIVE_STATUSES: TrainingJobStatus[] = [
  "pending",
  "queued",
  "uploading",
  "running",
  "cancelling",
];

type TrainingSummaryStatus = "editing" | "pending" | "success" | "failed";

const summaryStatusForJob = (job: TrainingJob): TrainingSummaryStatus => {
  const status = displayStatus(job);
  if (status === "editing") return "editing";
  return status === "success" || status === "failed" ? status : "pending";
};

const elapsedForJob = (job: TrainingJob) => {
  if (job.runtime_seconds) return job.runtime_seconds;
  if (job.started_at && ACTIVE_STATUSES.includes(job.status)) {
    return Math.max(
      Math.floor((Date.now() - new Date(job.started_at).getTime()) / 1000),
      0,
    );
  }
  return 0;
};

const displayStatus = (job: TrainingJob) => {
  if (job.deletion_pending) return "deleting";
  if (job.status === "editing") return "editing";
  if (job.status === "completed") return "success";
  if (job.status === "failed" || job.status === "cancelled") return "failed";
  return "pending";
};

export default function TrainingModelPage() {
  const { modelId } = useParams();
  const { t, i18n } = useTranslation("training");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [projectFilter, setProjectFilter] = useState(modelId ?? "all");
  const { data: projects } = useQuery({ queryKey: ["training", "projects"], queryFn: listModelProjects });
  const [statusFilter, setStatusFilter] = useState<TrainingStatusFilter>("all");
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
  const { data: usage, isLoading: isUsageLoading, isError: isUsageError } = useQuery({
    queryKey: trainingQueryKeys.usage(),
    queryFn: getTrainingUsage,
    refetchInterval: 15000,
  });

  const allTrainingJobs = useMemo(
    () => data?.training_jobs ?? [],
    [data?.training_jobs],
  );
  const selectedModelTrainingJobs = useMemo(
    () =>
      projectFilter === "all" ? allTrainingJobs : allTrainingJobs.filter((job) => projectFilter === "unassigned" ? !job.project_id : job.project_id === projectFilter),
    [allTrainingJobs, projectFilter],
  );
  const statusOptions = useMemo<SelectOption[]>(
    () => [
      { value: "all", label: t("statusFilter.all") },
      { value: "editing", label: t("statusFilter.editing") },
      { value: "pending", label: t("statusFilter.pending") },
      { value: "success", label: t("statusFilter.success") },
      { value: "failed", label: t("statusFilter.failed") },
    ],
    [t],
  );

  const trainingJobs = useMemo(
    () =>
      selectedModelTrainingJobs.filter((job) => {
        const status = displayStatus(job);
        return (
          statusFilter === "all" ||
          (status === "deleting" ? "pending" : status) === statusFilter
        );
      }),
    [selectedModelTrainingJobs, statusFilter],
  );
  const trainingStatusSummary = useMemo(() => {
    const total = selectedModelTrainingJobs.length;
    const counts: Record<TrainingSummaryStatus, number> = {
      editing: 0,
      pending: 0,
      success: 0,
      failed: 0,
    };

    selectedModelTrainingJobs.forEach((job) => {
      counts[summaryStatusForJob(job)] += 1;
    });

    return (
      Object.entries(counts) as Array<[TrainingSummaryStatus, number]>
    ).map(([status, count]) => ({
      status,
      count,
      percentage: total ? (count / total) * 100 : 0,
    }));
  }, [selectedModelTrainingJobs]);

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
      void queryClient.invalidateQueries({ queryKey: trainingQueryKeys.usage() });
      void queryClient.invalidateQueries({
        queryKey: trainingQueryKeys.jobs(),
      });
      navigate(`/dashboard/training/${newJob.id}/workspace${sourceJob.project_id ? `?project=${sourceJob.project_id}` : ""}`);
    },
    onError: (error) => {
      toast.error(
        getTrainingStartError(error, t, i18n.language),
      );
    },
  });

  const columns = useMemo<ColumnDef<TrainingJob>[]>(
    () => [
      {
        accessorKey: "id",
        header: t("detail.overview.internalJobId"),
        cell: ({ row }) => (
          <button
            type="button"
            className="break-all text-left font-medium hover:text-color-primary"
            onClick={() => navigate(`/dashboard/training/${row.original.id}/workspace`)}
          >
            {row.original.id}
          </button>
        ),
      },
      {
        accessorKey: "project_id",
        header: t("studio.project"),
        cell: ({ row }) => projects?.models.find((project) => project.id === row.original.project_id)?.name ?? t("studio.unassigned"),
      },
      {
        accessorKey: "started_at",
        header: t("table.trainingAt"),
        cell: ({ row }) => (
          <button
            type="button"
            className="text-left font-medium hover:text-color-primary transition-colors focus:outline-none"
            onClick={() =>
              navigate(`/dashboard/training/${row.original.id}/workspace`)
            }
          >
            {row.original.started_at
              ? formatDateTime(row.original.started_at, i18n.language)
              : "—"}
          </button>
        ),
      },
      {
        accessorKey: "model_flavor",
        header: t("table.flavor"),
        cell: ({ row }) => (
          <Badge variant="neutral">
            {t(`table.flavors.${row.original.model_flavor}`)}
          </Badge>
        ),
      },
      {
        accessorKey: "model_status",
        header: t("table.modelStatus"),
        cell: ({ row }) => {
          const modelStatus = row.original.model_status ?? "none";
          const variant =
            modelStatus === "deployed"
              ? "success"
              : modelStatus === "built"
                ? "primary"
                : modelStatus === "trained"
                  ? "warning"
                  : "neutral";
          return (
            <Badge variant={variant}>
              {t(`table.modelStatuses.${modelStatus}`)}
            </Badge>
          );
        },
      },
      {
        id: "accelerators",
        header: t("table.accelerators"),
        enableSorting: false,
        cell: ({ row }) => {
          const job = row.original;
          if (job.vcpu == null || job.memory_mb == null) return "—";
          const digits = job.memory_mb % 1024 === 0 ? 0 : 1;
          const memoryGb = formatNumber(job.memory_mb / 1024, i18n.language, {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
          });
          const gpu =
            job.accelerator_type === "gpu" && job.accelerator_count > 0
              ? ` · ${job.accelerator_model === "t4" ? "NVIDIA T4" : job.accelerator_model === "a10g" ? "NVIDIA A10G" : "GPU"} ×${job.accelerator_count}`
              : "";
          return `${job.vcpu} vCPU · ${memoryGb} GB${gpu}`;
        },
      },
      {
        id: "runtime",
        header: t("table.runtime"),
        accessorFn: elapsedForJob,
        cell: ({ row }) => formatDuration(elapsedForJob(row.original)),
      },
      {
        id: "status",
        header: t("table.status"),
        accessorFn: displayStatus,
        cell: ({ row }) => {
          const status = displayStatus(row.original);
          const variant =
            status === "success"
              ? "success"
              : status === "failed"
                ? "danger"
                : status === "deleting"
                  ? "warning"
                  : "neutral";
          return (
            <Badge variant={variant}>{t(`table.statuses.${status}`)}</Badge>
          );
        },
      },
      {
        id: "actions",
        header: t("table.actions"),
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
                aria-label={t("training:table.view")}
                title={t("training:table.view")}
                icon={<Eye className="h-4 w-4" />}
                disabled={deleting}
                onClick={() =>
                  navigate(`/dashboard/training/${job.id}/workspace`)
                }
              />
              {(job.status === "failed" || job.status === "cancelled") && (
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label={t("training:retryJob")}
                  title={t("training:retryJob")}
                  icon={<RotateCcw className="h-4 w-4" />}
                  disabled={deleting || retryMutation.isPending}
                  onClick={() => setJobToRetry(job)}
                />
              )}
              <Button
                size="icon"
                variant="ghost"
                aria-label={t("training:table.delete")}
                title={t("training:table.delete")}
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
      <div className="flex flex-wrap gap-3">
        <label className="space-y-2 text-style-body-strong"><span>{t("studio.project")}</span><select className="block h-11 rounded-control border border-input bg-surface px-3 text-style-body" value={projectFilter} onChange={(event) => setProjectFilter(event.target.value)}><option value="all">{t("studio.allProjects")}</option><option value="unassigned">{t("studio.unassigned")}</option>{projects?.models.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-surface border border-border bg-surface p-5 shadow-sm md:col-span-2">
          <p className="text-style-overline uppercase text-color-muted-foreground">{t("quota")}</p>
          {isUsageLoading && <p>...</p>}
          {isUsageError && <p className="text-style-caption text-color-danger">{t("quotaUnavailable")}</p>}
          {usage && <p className="text-style-caption text-color-muted-foreground">{t("quotaReset", { time: formatDateTime(usage.reset_at, i18n.language) })}</p>}
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {usage?.resources.map((item) => (
              <div key={item.resource} className="rounded-surface border border-border p-3">
                <p className="text-style-caption-strong">{t(`quotaProfiles.${item.resource}`)}</p>
                <p className="text-style-body-strong">{item.remaining_seconds == null ? t("quotaUnlimited") : formatQuotaDuration(item.remaining_seconds)}</p>
                {item.limit_seconds != null && <p className="text-style-caption text-color-muted-foreground">
                  {formatQuotaDuration(item.used_seconds)} / {formatQuotaDuration(item.limit_seconds)} · {t("quotaReserved", { duration: formatQuotaDuration(item.reserved_seconds) })}
                </p>}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-surface border border-border bg-surface p-5 shadow-sm">
          <p className="flex items-center gap-2 text-style-overline uppercase text-color-muted-foreground">
            {t("totalJobs")}
          </p>
          <span className="mt-3 text-style-page-title font-semibold text-color-foreground">
            {selectedModelTrainingJobs.filter((job) => Boolean(job.submitted_at)).length}
          </span>
          <p className="mt-2 text-style-caption">{t("studio.draftCount", { count: selectedModelTrainingJobs.filter((job) => job.status === "editing").length })}</p>
          <div
            className="mt-4 flex h-2.5 overflow-hidden rounded-full bg-muted"
            aria-label={t("statusDistribution.label")}
            role="img"
          >
            {trainingStatusSummary.some(({ count }) => count > 0) ? (
              trainingStatusSummary.map(({ status, percentage }) => (
                <span
                  key={status}
                  tabIndex={0}
                  title={t("statusDistribution.tooltip", {
                    status: t(`table.statuses.${status}`),
                    percentage: formatNumber(percentage, i18n.language, {
                      minimumFractionDigits: 1,
                      maximumFractionDigits: 1,
                    }),
                  })}
                  aria-label={t("statusDistribution.tooltip", {
                    status: t(`table.statuses.${status}`),
                    percentage: formatNumber(percentage, i18n.language, {
                      minimumFractionDigits: 1,
                      maximumFractionDigits: 1,
                    }),
                  })}
                  className={
                    status === "success"
                      ? "h-full bg-success outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      : status === "failed"
                        ? "h-full bg-danger outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        : "h-full bg-primary outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  }
                  style={{ width: `${percentage}%` }}
                />
              ))
            ) : (
              <span
                className="h-full w-full"
                title={t("statusDistribution.empty")}
              />
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="w-full sm:w-60">
          <Select
            className="h-10 text-style-body"
            value={statusFilter}
            onChange={(val) => setStatusFilter(val as TrainingStatusFilter)}
            options={statusOptions}
            placeholder={t("statusFilter.placeholder")}
          />
        </div>
        <Button
          size="md"
          icon={<Plus className="h-4 w-4" />}
          onClick={() => navigate(`/dashboard/training/new${modelId ? `?project=${modelId}` : ""}`)}
        >
          {t("newJob")}
        </Button>
      </div>

      {isError && (
        // A failed background refresh (the list polls while jobs run) keeps the last loaded
        // jobs on screen; only a failed first load, with nothing to show, replaces the table.
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
