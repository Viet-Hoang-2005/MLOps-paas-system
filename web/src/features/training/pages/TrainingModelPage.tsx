import { RouteFallback } from "@/app/router/RouteFallback";
import { NoProjectPlaceholder } from "@/features/projects/components/NoProjectPlaceholder";
import { formatDateTime, formatNumber } from "@/shared/i18n/formatters";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { BrainCircuit, Eye, Rocket, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import {
  deleteTrainingJob,
  getTrainingUsage,
  listTrainingJobs,
} from "@/features/training/api/trainingApi";
import {
  TrainingJobStatusFilter,
  type TrainingStatusFilter,
} from "@/features/training/components/TrainingJobListSections";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import type { TrainingJob, TrainingJobStatus } from "@/features/training/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { Table } from "@/shared/components/Table";
import { formatDuration } from "@/shared/lib/formatDuration";
import { toast } from "@/shared/types/toastStore";

const ACTIVE_STATUSES: TrainingJobStatus[] = [
  "pending",
  "queued",
  "uploading",
  "running",
  "cancelling",
];

type TrainingSummaryStatus = "pending" | "success" | "failed";

const summaryStatusForJob = (job: TrainingJob): TrainingSummaryStatus => {
  const status = displayStatus(job);
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
  if (job.status === "completed") return "success";
  if (job.status === "failed" || job.status === "cancelled") return "failed";
  return "pending";
};

export default function TrainingModelPage() {
  const { modelId } = useParams();
  const { t, i18n } = useTranslation("training");
  const { t: tCommon } = useTranslation("common");
  const { t: tProjects } = useTranslation("projects");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { selectedModel, loading: isModelLoading } = useModelSelection();
  const [statusFilter, setStatusFilter] = useState<TrainingStatusFilter>("all");
  const [jobToDelete, setJobToDelete] = useState<TrainingJob | null>(null);
  const pendingDeletionIds = useRef<Set<string>>(new Set());

  const {
    data,
    error: jobsError,
    isError,
    isLoading,
  } = useQuery({
    queryKey: trainingQueryKeys.jobs(),
    queryFn: () => listTrainingJobs(),
    refetchInterval: (query) => {
      const jobs = query.state.data?.training_jobs ?? [];
      return jobs.some(
        (job) =>
          (job.deletion_pending && !job.deletion_error) ||
          ACTIVE_STATUSES.includes(job.status),
      )
        ? 4000
        : false;
    },
  });
  const { data: usage, isLoading: isUsageLoading } = useQuery({
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
      selectedModel
        ? allTrainingJobs.filter((job) => job.project_id === selectedModel.id)
        : [],
    [allTrainingJobs, selectedModel],
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

  const columns = useMemo<ColumnDef<TrainingJob>[]>(
    () => [
      {
        accessorKey: "started_at",
        header: t("table.trainingAt"),
        cell: ({ row }) => (
          <button
            type="button"
            className="text-left font-medium hover:text-color-primary transition-colors focus:outline-none"
            onClick={() =>
              navigate(`/dashboard/training/jobs/${row.original.id}/overview`)
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
          const digits = job.memory_mb % 1024 === 0 ? 0 : 1;
          const memoryGb = formatNumber(job.memory_mb / 1024, i18n.language, {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
          });
          const gpu =
            job.accelerator_type === "gpu" && job.accelerator_count > 0
              ? ` · GPU ×${job.accelerator_count}`
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
                  navigate(`/dashboard/training/jobs/${job.id}/overview`)
                }
              />
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
    [navigate, t, i18n.language],
  );

  if (!selectedModel) {
    if (isModelLoading) return <RouteFallback />;
    return (
      <section className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader title={t("title")} />
        <NoProjectPlaceholder
          title={tCommon("navigation.modelTraining")}
          description={tProjects("workflow.noProjectTraining")}
          icon={<BrainCircuit className="h-6 w-6" />}
        />
      </section>
    );
  }

  if (!modelId) {
    return (
      <Navigate
        to={`/dashboard/projects/${selectedModel.id}/training`}
        replace
      />
    );
  }

  return (
    <section className="flex w-full flex-1 flex-col space-y-6">
      <PageHeader title={t("title")} />

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-surface border border-border bg-surface p-5 shadow-sm md:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-style-overline uppercase text-color-muted-foreground">
                {t("quota")}
              </p>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-style-page-title font-semibold text-color-foreground">
                  {isUsageLoading
                    ? "..."
                    : formatDuration(usage?.monthly_runtime_seconds)}
                </span>
                <span className="text-style-body-strong text-color-muted-foreground">
                  {t("used", {
                    duration: formatDuration(
                      usage?.monthly_quota_seconds || 43200,
                    ),
                  })}
                </span>
              </div>
            </div>
            <div className="text-right">
              <p className="text-style-overline uppercase text-color-muted-foreground">
                {t("remaining")}
              </p>
              <p className="mt-1 text-style-heading font-semibold text-color-success">
                {isUsageLoading
                  ? "..."
                  : formatDuration(usage?.remaining_seconds)}
              </p>
            </div>
          </div>
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-success transition-all duration-500 ease-out"
              style={{
                width: `${Math.min(
                  100,
                  ((usage?.monthly_runtime_seconds || 0) /
                    (usage?.monthly_quota_seconds || 1)) *
                    100,
                )}%`,
              }}
            />
          </div>
        </div>

        <div className="rounded-surface border border-border bg-surface p-5 shadow-sm">
          <p className="flex items-center gap-2 text-style-overline uppercase text-color-muted-foreground">
            {t("totalJobs")}
          </p>
          <span className="mt-3 text-style-page-title font-semibold text-color-foreground">
            {selectedModelTrainingJobs.length}
          </span>
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
        <TrainingJobStatusFilter
          value={statusFilter}
          onChange={setStatusFilter}
        />
        <Button
          size="md"
          icon={<Rocket className="h-4 w-4" />}
          onClick={() => navigate("/dashboard/training/new/metadata")}
        >
          {t("newJob")}
        </Button>
      </div>

      {isError ? (
        <div className="rounded-surface border border-danger/20 bg-danger-subtle p-5">
          <p className="text-style-body text-color-danger">
            {getApiErrorMessage(jobsError, t("checkApi"))}
          </p>
        </div>
      ) : (
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
        description={t("delete.description", { job: jobToDelete?.name ?? "" })}
        confirmText={t("delete.confirm")}
        tone="danger"
        loading={deleteMutation.isPending}
        onCancel={() => setJobToDelete(null)}
        onConfirm={() => {
          if (jobToDelete) deleteMutation.mutate(jobToDelete);
        }}
      />
    </section>
  );
}
