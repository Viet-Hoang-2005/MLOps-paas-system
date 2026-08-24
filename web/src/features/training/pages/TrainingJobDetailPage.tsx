import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  Outlet,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bot,
  Download,
  FileArchive,
  Info,
  RefreshCw,
  ScrollText,
  Settings,
  Trash2,
} from "lucide-react";

import {
  buildAndRegisterTrainingJob,
  deleteTrainingJob,
  deleteTrainingOutputs,
  getTrainingJob,
  getTrainingJobDownloadUrl,
  getTrainingJobEvents,
  getTrainingJobLogs,
  getTrainingJobMetrics,
  refreshTrainingJobStatus,
} from "@/features/training/api/trainingApi";
import { LiveStatusBadge } from "@/features/training/components/TrainingOverviewSections";
import { trainingQueryKeys } from "@/features/training/queryKeys";
import type {
  TrainingJob,
  TrainingJobStatus,
} from "@/features/training/types";
import type {
  TrainingJobDetailContextValue,
  TrainingJobDetailSection,
} from "@/features/training/trainingJobDetailContext";
import { getApiErrorMessage } from "@/shared/api/errors";
import { computeElapsed, formatDuration } from "@/shared/lib/formatDuration";
import { Button } from "@/shared/components/Button";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { PageTabs } from "@/shared/components/PageTabs";
import { toast } from "@/shared/components/toastStore";

const ACTIVE_STATUSES: TrainingJobStatus[] = [
  "pending",
  "queued",
  "uploading",
  "running",
  "cancelling",
];
const DETAIL_SECTIONS: TrainingJobDetailSection[] = [
  "overview",
  "logs",
  "metrics",
  "artifacts",
  "config",
];
const AUTO_SYNC_INTERVAL_MS = 3000;

export default function TrainingJobDetailPage() {
  const { t } = useTranslation("training");
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const parsedJobId = jobId ?? "";
  const pathnameSection = location.pathname.split("/").filter(Boolean).at(-1);
  const activeSection = DETAIL_SECTIONS.includes(
    pathnameSection as TrainingJobDetailSection,
  )
    ? (pathnameSection as TrainingJobDetailSection)
    : "overview";
  const [refreshingSection, setRefreshingSection] = useState<
    "header" | "logs" | "metrics" | null
  >(null);
  const [deleteOutputsOpen, setDeleteOutputsOpen] = useState(false);
  const [deleteJobOpen, setDeleteJobOpen] = useState(false);
  const [liveElapsed, setLiveElapsed] = useState<number | null>(null);
  const lastToastedStatus = useRef<string | null>(null);

  const statusLabels: Record<TrainingJobStatus, string> = {
    pending: t("detail.statuses.pending"),
    queued: t("detail.statuses.queued"),
    uploading: t("detail.statuses.uploading"),
    running: t("detail.statuses.running"),
    cancelling: t("detail.statuses.cancelling"),
    completed: t("detail.statuses.completed"),
    failed: t("detail.statuses.failed"),
    cancelled: t("detail.statuses.cancelled"),
  };

  const {
    data: job,
    isLoading: jobLoading,
    error: jobError,
    refetch: refetchJob,
  } = useQuery({
    queryKey: trainingQueryKeys.job(parsedJobId),
    queryFn: () => getTrainingJob(parsedJobId),
    enabled: Boolean(parsedJobId),
    refetchInterval: (query) => {
      const currentJob = query.state.data;
      return currentJob && ACTIVE_STATUSES.includes(currentJob.status)
        ? AUTO_SYNC_INTERVAL_MS
        : false;
    },
  });

  const {
    data: logsResponse,
    isLoading: loadingLogs,
    refetch: refetchLogs,
  } = useQuery({
    queryKey: trainingQueryKeys.logs(parsedJobId),
    queryFn: () => getTrainingJobLogs(parsedJobId),
    enabled: Boolean(job) && activeSection === "logs",
    refetchInterval:
      job &&
      activeSection === "logs" &&
      ACTIVE_STATUSES.includes(job.status)
        ? AUTO_SYNC_INTERVAL_MS
        : false,
  });

  const {
    data: metrics,
    isLoading: loadingMetrics,
    refetch: refetchMetrics,
  } = useQuery({
    queryKey: trainingQueryKeys.metrics(parsedJobId),
    queryFn: () => getTrainingJobMetrics(parsedJobId),
    enabled: Boolean(job) && activeSection === "metrics",
    refetchInterval:
      job &&
      activeSection === "metrics" &&
      ACTIVE_STATUSES.includes(job.status)
        ? AUTO_SYNC_INTERVAL_MS
        : false,
  });

  const { data: eventsResponse, refetch: refetchEvents } = useQuery({
    queryKey: trainingQueryKeys.events(parsedJobId),
    queryFn: () => getTrainingJobEvents(parsedJobId),
    enabled: Boolean(job) && activeSection === "logs",
    refetchInterval:
      job &&
      activeSection === "logs" &&
      ACTIVE_STATUSES.includes(job.status)
        ? AUTO_SYNC_INTERVAL_MS
        : false,
  });

  useEffect(() => {
    if (!job?.status) return;
    const previousStatus = lastToastedStatus.current;
    if (previousStatus && previousStatus !== job.status) {
      if (job.status === "completed")
        toast.success(t("detail.completedToast"));
      else if (job.status === "failed") toast.error(t("detail.failedToast"));
      else if (job.status === "cancelled")
        toast.warning(t("detail.cancelledToast"));
    }
    lastToastedStatus.current = job.status;
  }, [job?.status, t]);

  useEffect(() => {
    if (!job || job.status !== "running" || !job.started_at) return;
    const startedAt = job.started_at;
    const tick = () => {
      const elapsed = computeElapsed(startedAt);
      setLiveElapsed(elapsed != null ? Math.round(elapsed) : null);
    };
    tick();
    const intervalId = window.setInterval(tick, 1000);
    return () => {
      window.clearInterval(intervalId);
      setLiveElapsed(null);
    };
  }, [job]);

  const refreshStatusMutation = useMutation({
    mutationFn: () => refreshTrainingJobStatus(parsedJobId),
    onSuccess: (updatedJob) => {
      queryClient.setQueryData(
        trainingQueryKeys.job(parsedJobId),
        updatedJob,
      );
      if (activeSection === "logs") {
        void refetchLogs();
        void refetchEvents();
      }
      if (activeSection === "metrics") void refetchMetrics();
      toast.success(t("detail.refreshed"));
    },
    onError: (error) =>
      toast.error(getApiErrorMessage(error, t("detail.refreshFailed"))),
  });

  const downloadMutation = useMutation({
    mutationFn: () => getTrainingJobDownloadUrl(parsedJobId),
    onSuccess: ({ download_url: downloadUrl }) => {
      const link = document.createElement("a");
      link.href = downloadUrl;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    },
    onError: (error) =>
      toast.error(getApiErrorMessage(error, t("detail.downloadFailed"))),
  });

  const deleteJobMutation = useMutation({
    mutationFn: () => deleteTrainingJob(parsedJobId),
    onSuccess: async () => {
      setDeleteJobOpen(false);
      toast.warning(t("delete.requested"));
      await queryClient.invalidateQueries({
        queryKey: trainingQueryKeys.jobs(),
      });
      navigate("/dashboard/model-training");
    },
    onError: (error) =>
      toast.error(getApiErrorMessage(error, t("delete.failed"))),
  });

  const buildAndRegisterMutation = useMutation({
    mutationFn: () => buildAndRegisterTrainingJob(parsedJobId),
    onSuccess: async () => {
      toast.success(t("detail.buildStarted"));
      await refetchJob();
      await queryClient.invalidateQueries({
        queryKey: trainingQueryKeys.jobs(),
      });
    },
    onError: (error) =>
      toast.error(getApiErrorMessage(error, t("detail.buildFailed"))),
  });

  const deleteOutputsMutation = useMutation({
    mutationFn: () => deleteTrainingOutputs(parsedJobId),
    onSuccess: async (updatedJob) => {
      setDeleteOutputsOpen(false);
      queryClient.setQueryData(
        trainingQueryKeys.job(parsedJobId),
        updatedJob,
      );
      await queryClient.invalidateQueries({
        queryKey: trainingQueryKeys.jobs(),
      });
      toast.success(t("detail.outputsDeleted"));
    },
    onError: (error) =>
      toast.error(getApiErrorMessage(error, t("detail.outputDeleteFailed"))),
  });

  const refreshHeader = async () => {
    setRefreshingSection("header");
    try {
      await refreshStatusMutation.mutateAsync();
    } finally {
      setRefreshingSection(null);
    }
  };

  const refreshLogs = async () => {
    setRefreshingSection("logs");
    try {
      await Promise.all([refetchLogs(), refetchEvents()]);
    } finally {
      setRefreshingSection(null);
    }
  };

  const refreshMetrics = async () => {
    setRefreshingSection("metrics");
    try {
      await refetchMetrics();
    } finally {
      setRefreshingSection(null);
    }
  };

  const copyUri = useCallback(
    (value: string) => {
      void navigator.clipboard.writeText(value);
      toast.success(t("detail.copied"));
    },
    [t],
  );

  if (!parsedJobId) {
    return (
      <div className="flex h-[80vh] items-center justify-center">
        <p className="text-style-heading font-medium text-color-muted-foreground">
          {t("detail.invalidId")}
        </p>
      </div>
    );
  }

  if (jobLoading) {
    return (
      <div className="flex h-[80vh] flex-col items-center justify-center gap-4">
        <RefreshCw className="h-8 w-8 animate-spin text-color-primary" />
        <p className="font-medium text-color-muted-foreground">
          {t("detail.loading")}
        </p>
      </div>
    );
  }

  if (jobError || !job) {
    return (
      <div className="flex h-[80vh] flex-col items-center justify-center gap-4">
        <div className="rounded-full bg-danger-subtle p-4">
          <AlertTriangle className="h-10 w-10 text-color-danger" />
        </div>
        <p className="text-style-heading font-bold text-color-foreground">
          {t("detail.notFound")}
        </p>
        <p className="max-w-md text-center text-color-muted-foreground">
          {t("detail.notFoundDescription")}
        </p>
        <Button
          onClick={() => navigate("/dashboard/model-training")}
          variant="secondary"
          className="mt-2"
        >
          {t("detail.backHistory")}
        </Button>
      </div>
    );
  }

  const elapsedSeconds = getElapsedSeconds(job, liveElapsed);
  const tabs = [
    { id: "overview", label: t("detail.tabs.overview"), icon: Info },
    { id: "logs", label: t("detail.tabs.logs"), icon: ScrollText },
    { id: "metrics", label: t("detail.tabs.metrics"), icon: Activity },
    {
      id: "artifacts",
      label: t("detail.tabs.artifacts"),
      icon: FileArchive,
    },
    { id: "config", label: t("detail.tabs.config"), icon: Settings },
  ] as const;
  const context: TrainingJobDetailContextValue = {
    job,
    statusLabels,
    activeStatuses: ACTIVE_STATUSES,
    logsResponse,
    loadingLogs,
    metrics,
    loadingMetrics,
    eventsResponse,
    refreshingSection,
    refreshLogs,
    refreshMetrics,
    refreshJob: async () => {
      await refetchJob();
    },
    downloadOutput: () => downloadMutation.mutate(),
    downloadingOutput: downloadMutation.isPending,
    buildAndRegister: () => buildAndRegisterMutation.mutate(),
    buildingAndRegistering: buildAndRegisterMutation.isPending,
    requestDeleteOutputs: () => setDeleteOutputsOpen(true),
    copyUri,
  };

  return (
    <section className="flex w-full flex-1 flex-col space-y-6">
      <button
        type="button"
        onClick={() => navigate("/dashboard/model-training")}
        className="group mb-6 flex items-center gap-2 text-style-body-strong text-color-muted-foreground transition-colors hover:text-color-foreground"
      >
        <ArrowLeft className="h-4 w-4 transition-all group-hover:-translate-x-0.5" />
        {t("detail.backTraining")}
      </button>

      <div className="overflow-hidden rounded-surface border border-border bg-surface shadow-sm transition-shadow hover:shadow-md">
        <div className="flex flex-col gap-6 border-b border-border p-6 sm:flex-row sm:items-start sm:justify-between lg:p-8">
          <div className="flex min-w-0 items-start gap-4">
            <div className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-surface border border-border bg-muted text-color-muted-foreground shadow-inner sm:flex">
              <Bot className="h-6 w-6" />
            </div>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-style-page-title font-bold text-color-foreground">
                {job.name}
              </h1>
              <p className="mt-1 text-style-caption-strong text-color-muted-foreground">
                {t("detail.jobNumber", { id: job.id })}
              </p>
            </div>
          </div>

          <div className="flex shrink-0 flex-col items-end gap-3 sm:flex-row sm:items-center">
            {ACTIVE_STATUSES.includes(job.status) && <LiveStatusBadge />}
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button
                size="icon"
                variant="secondary"
                icon={
                  <RefreshCw
                    className={`h-4 w-4 ${
                      refreshingSection === "header" ? "animate-spin" : ""
                    }`}
                  />
                }
                disabled={refreshingSection === "header"}
                onClick={() => void refreshHeader()}
                aria-label={t("detail.refreshStatus")}
                title={t("detail.refreshStatus")}
                className="rounded-surface border border-border shadow-sm transition-all hover:border-foreground/30"
              />
              <Button
                size="icon"
                variant={job.status === "completed" ? "primary" : "secondary"}
                icon={<Download className="h-4 w-4" />}
                disabled={
                  job.status !== "completed" || downloadMutation.isPending
                }
                onClick={() => downloadMutation.mutate()}
                aria-label={t("detail.download")}
                title={t("detail.download")}
                className="rounded-surface border border-border shadow-sm transition-all hover:border-foreground/30"
              />
              <Button
                size="icon"
                variant="ghost"
                icon={<Trash2 className="h-4 w-4" />}
                disabled={job.deletion_pending || deleteJobMutation.isPending}
                onClick={() => setDeleteJobOpen(true)}
                aria-label={t("table.delete")}
                title={t("table.delete")}
                className="rounded-surface border border-danger/30 text-color-danger shadow-sm transition-all hover:border-danger hover:bg-danger-subtle hover:text-color-danger"
              />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-y divide-border bg-muted/50 lg:grid-cols-4 lg:divide-x lg:divide-y-0">
          <SummaryCell label={t("table.status", { defaultValue: "Training Status" })}>
            <span className={statusBadgeClass(job.status)}>
              {statusLabels[job.status]}
            </span>
          </SummaryCell>
          <SummaryCell label={t("detail.runtimeElapsed")}>
            <p className="text-style-section-title font-bold text-color-foreground">
              {formatDuration(elapsedSeconds) || "-"}
              {job.status === "running" && (
                <span className="ml-1 animate-pulse text-style-caption font-normal text-color-primary">
                  {t("detail.live")}
                </span>
              )}
            </p>
          </SummaryCell>
          <SummaryCell label={t("table.modelStatus")}>
            <span className={modelStatusBadgeClass(job.model_status ?? "none")}>
              {t(`table.modelStatuses.${job.model_status ?? "none"}`)}
            </span>
          </SummaryCell>
          <SummaryCell label={t("detail.overview.updatedAt")}>
            <p className="text-style-section-title font-bold text-color-foreground">
              {new Date(job.updated_at).toLocaleString()}
            </p>
          </SummaryCell>
        </div>
      </div>

      <div className="mt-2 border-b border-border">
        <PageTabs
          tabs={tabs.map((tab) => ({
            label: tab.label,
            icon: tab.icon,
            isActive: activeSection === tab.id,
            onClick: () =>
              navigate(
                `/dashboard/model-training/jobs/${job.id}/details/${tab.id}`,
              ),
          }))}
        />
      </div>

      <div className="min-h-100">
        <Outlet context={context} />
      </div>

      <ConfirmModal
        open={deleteJobOpen}
        title={t("delete.title")}
        description={t("delete.description", { job: job.name })}
        confirmText={t("delete.confirm")}
        tone="danger"
        loading={deleteJobMutation.isPending}
        onCancel={() => setDeleteJobOpen(false)}
        onConfirm={() => deleteJobMutation.mutate()}
      />
      <ConfirmModal
        open={deleteOutputsOpen}
        title={t("detail.deleteOutputTitle")}
        description={t("detail.deleteOutputDescription")}
        confirmText={t("detail.deleteOutputConfirm")}
        tone="danger"
        loading={deleteOutputsMutation.isPending}
        onCancel={() => setDeleteOutputsOpen(false)}
        onConfirm={() => deleteOutputsMutation.mutate()}
      />
    </section>
  );
}

function getElapsedSeconds(job: TrainingJob, liveElapsed: number | null) {
  if (job.status === "running" && liveElapsed != null) return liveElapsed;
  if (job.runtime_seconds) return Math.round(job.runtime_seconds);
  if (job.completed_at && job.started_at) {
    return Math.round(
      (new Date(job.completed_at).getTime() -
        new Date(job.started_at).getTime()) /
        1000,
    );
  }
  return null;
}

function SummaryCell({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col justify-center p-5">
      <p className="mb-1.5 text-style-caption font-bold uppercase text-color-muted-foreground">
        {label}
      </p>
      <div className="flex items-center">{children}</div>
    </div>
  );
}

function statusBadgeClass(status: TrainingJobStatus) {
  const base = "w-fit rounded-compact border px-2.5 py-0.5 text-style-body-strong";
  if (status === "completed")
    return `${base} border-success/20 bg-success-subtle text-color-success`;
  if (status === "failed")
    return `${base} border-danger/20 bg-danger-subtle text-color-danger`;
  if (status === "cancelled")
    return `${base} border-warning/20 bg-warning-subtle text-color-warning`;
  if (status === "running")
    return `${base} border-primary/20 bg-primary-subtle text-color-primary`;
  return `${base} border-border bg-surface text-color-foreground`;
}

function modelStatusBadgeClass(status: TrainingJob["model_status"]) {
  const base = "w-fit rounded-compact border px-2.5 py-0.5 text-style-body-strong";
  if (status === "deployed")
    return `${base} border-success/20 bg-success-subtle text-color-success`;
  if (status === "built")
    return `${base} border-primary/20 bg-primary-subtle text-color-primary`;
  if (status === "trained")
    return `${base} border-warning/20 bg-warning-subtle text-color-warning`;
  return `${base} border-border bg-surface text-color-foreground`;
}
