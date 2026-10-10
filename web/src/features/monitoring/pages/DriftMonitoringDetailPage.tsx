import { RouteFallback } from "@/app/router/RouteFallback";
import {
  useCancelDriftMonitoringRun,
  useDeleteDriftMonitoringJob,
  useDeleteDriftMonitoringRun,
  useDriftMonitor,
  useDriftMonitoringJobs,
  useDriftMonitoringResults,
  useProductionDataCount,
  useRunDriftMonitoringJob,
  type DriftMonitoringResult,
} from "@/features/monitoring/hooks/useDriftMonitoring";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { CardSummary } from "@/shared/components/Card";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageBody } from "@/shared/components/PageBody";
import { PageHeader } from "@/shared/components/PageHeader";
import { Placeholder } from "@/shared/components/Placeholder";
import { StepTitle } from "@/shared/components/StepTitle";
import { Table } from "@/shared/components/Table";
import { TerminalViewer } from "@/shared/components/TerminalViewer";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { formatDateTime, formatNumber } from "@/shared/i18n/formatters";
import type { ColumnDef } from "@tanstack/react-table";
import { Edit, LineChart, Loader2, Play, Square, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

const DRIFT_TERMINAL_STATUSES = [
  "completed",
  "failed",
  "cancelled",
  "skipped",
] as const;

export default function DriftMonitoringDetailPage() {
  const { t, i18n } = useTranslation("monitoring");
  const { modelId, monitorId } = useParams<{
    modelId?: string;
    monitorId?: string;
  }>();
  const { selectedModel, loading: isModelLoading } = useModelSelection();
  const navigate = useNavigate();

  const effectiveModelId = modelId ?? selectedModel?.id;

  const { data: singleJob, isLoading: isLoadingSingleJob } =
    useDriftMonitor(monitorId);
  const { data: jobs, isLoading: isLoadingJobs } =
    useDriftMonitoringJobs(effectiveModelId);

  const activeJob = singleJob ?? jobs?.find((job) => job.id === monitorId);
  const projectIdForJob = effectiveModelId ?? activeJob?.project_id;

  const {
    data: results,
    isLoading: isLoadingResults,
    refetch: refetchResults,
  } = useDriftMonitoringResults(activeJob?.id);

  const { data: productionDataCount } = useProductionDataCount(
    projectIdForJob,
    activeJob?.version_id,
  );

  const { mutate: deleteJob, isPending: isDeletingJob } =
    useDeleteDriftMonitoringJob();
  const { mutate: deleteRun, isPending: isDeletingRun } =
    useDeleteDriftMonitoringRun(activeJob?.id);
  const { mutateAsync: runJob, isPending: isRunning } =
    useRunDriftMonitoringJob();
  const { mutateAsync: cancelRun, isPending: isCancelling } =
    useCancelDriftMonitoringRun(activeJob?.id);

  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [runToDelete, setRunToDelete] = useState<DriftMonitoringResult | null>(
    null,
  );
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const effectiveRunId = activeRunId ?? results?.[0]?.id ?? null;

  const stream = useRuntimeLogStream({
    source: effectiveRunId ? { kind: "drift", id: effectiveRunId } : null,
    enabled: Boolean(effectiveRunId),
    terminalStatuses: DRIFT_TERMINAL_STATUSES,
  });

  const activeRun = effectiveRunId
    ? results?.find((r) => r.id === effectiveRunId) ?? results?.[0]
    : results?.[0];

  const currentRunStatus =
    (effectiveRunId && stream.status ? stream.status : null) ||
    activeRun?.status;

  const isRunActive = Boolean(
    isRunning ||
    (currentRunStatus &&
      ["pending", "queued", "running"].includes(currentRunStatus))
  );

  const statusBadge = currentRunStatus ? (
    <Badge
      variant={
        currentRunStatus === "completed"
          ? activeRun?.has_drift
            ? "danger"
            : "success"
          : currentRunStatus === "failed"
            ? "danger"
            : ["pending", "queued", "running"].includes(currentRunStatus)
              ? "info"
              : "warning"
      }
    >
      {currentRunStatus === "completed"
        ? activeRun?.has_drift
          ? t("driftDetected")
          : t("healthy")
        : t(currentRunStatus)}
    </Badge>
  ) : undefined;

  useEffect(() => {
    if (
      stream.status &&
      DRIFT_TERMINAL_STATUSES.includes(
        stream.status as (typeof DRIFT_TERMINAL_STATUSES)[number],
      )
    ) {
      void refetchResults();
    }
  }, [refetchResults, stream.status]);

  const handleRunNow = async () => {
    if (!activeJob) return;
    try {
      const run = await runJob({
        id: activeJob.id,
        project_id: projectIdForJob ?? activeJob.project_id,
      });
      setActiveRunId(run.id);
      void refetchResults();
    } catch {
      // Error handled by mutation toast
    }
  };

  const handleCancelRun = async () => {
    if (!activeJob) return;
    try {
      await cancelRun({
        monitorId: activeJob.id,
        runId: activeRun?.id ?? activeRunId ?? undefined,
      });
      void refetchResults();
    } catch {
      // Error handled by mutation toast
    }
  };

  const handleViewReport = (runId: string) => {
    if (projectIdForJob) {
      navigate(
        `/dashboard/projects/${projectIdForJob}/monitoring/report/${runId}`,
      );
    }
  };

  const handleBack = () => {
    if (projectIdForJob) {
      navigate(`/dashboard/projects/${projectIdForJob}/monitoring`);
    } else {
      navigate(-1);
    }
  };

  const totalRuns = results?.length ?? 0;
  const driftDetectedRuns =
    results?.filter((run) => run.has_drift === true).length ?? 0;
  const driftRate = totalRuns > 0 ? (driftDetectedRuns / totalRuns) * 100 : 0;

  const latestRunRecords =
    results?.[0]?.production_records ??
    (results?.[0]?.summary as { production_records?: number; samples?: number })
      ?.production_records ??
    (results?.[0]?.summary as { production_records?: number; samples?: number })
      ?.samples;

  const productionCount = productionDataCount ?? latestRunRecords ?? 0;

  if (isModelLoading || isLoadingSingleJob || (isLoadingJobs && !activeJob)) {
    return <RouteFallback />;
  }

  if (!activeJob) {
    return (
      <div className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader title={t("detailTitle")} back onBack={handleBack} />
        <Placeholder
          title={t("title")}
          description={t("jobNotFound")}
          icon={<LineChart className="h-6 w-6" />}
          action={
            <Button size="md" onClick={handleBack}>
              {t("backToMonitoring")}
            </Button>
          }
        />
      </div>
    );
  }

  const columns: ColumnDef<DriftMonitoringResult>[] = [
    {
      accessorKey: "id",
      header: t("runId"),
      cell: ({ row }) => (
        <button
          type="button"
          className="text-color-primary font-mono hover:underline disabled:text-color-muted-foreground disabled:no-underline"
          disabled={
            row.original.status !== "completed" || !row.original.report_html_uri
          }
          onClick={() => handleViewReport(row.original.id)}
        >
          {row.original.id}
        </button>
      ),
    },
    {
      accessorKey: "created_at",
      header: t("runAt"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap text-color-muted-foreground">
          {formatDateTime(row.original.created_at, i18n.language)}
        </span>
      ),
    },
    {
      id: "production_records",
      header: t("runProductionRecords"),
      cell: ({ row }) => {
        const count =
          row.original.production_records ??
          (
            row.original.summary as {
              production_records?: number;
              samples?: number;
            }
          )?.production_records ??
          (
            row.original.summary as {
              production_records?: number;
              samples?: number;
            }
          )?.samples;
        return (
          <span className="font-mono">
            {count != null ? formatNumber(count, i18n.language) : "—"}
          </span>
        );
      },
    },
    {
      accessorKey: "drift_score",
      header: t("driftScore"),
      cell: ({ row }) => (
        <span className="font-mono font-semibold">
          {row.original.drift_score == null
            ? t("none")
            : `${formatNumber(row.original.drift_score * 100, i18n.language, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`}
        </span>
      ),
    },
    {
      id: "status",
      header: t("status"),
      cell: ({ row }) => {
        if (row.original.status !== "completed")
          return <Badge variant="neutral">{row.original.status}</Badge>;
        return (
          <Badge variant={row.original.has_drift ? "danger" : "success"}>
            {row.original.has_drift ? t("driftDetected") : t("healthy")}
          </Badge>
        );
      },
    },
    {
      id: "actions",
      header: t("actionsHeader"),
      enableSorting: false,
      cell: ({ row }) => (
        <Button
          size="icon"
          variant="danger"
          border={false}
          icon={<Trash2 className="h-4 w-4" />}
          title={t("deleteRun")}
          aria-label={t("deleteRun")}
          onClick={() => setRunToDelete(row.original)}
        />
      ),
    },
  ];

  return (
    <div className="flex w-full flex-1 flex-col space-y-6">
      <PageHeader title={t("detailTitle")} back onBack={handleBack} />
      <PageBody className="p-6 space-y-6">
        <div className="flex flex-col space-y-4">
          <div className="flex justify-between items-start">
            <StepTitle
              title={t("configuration")}
              description={t("configurationDescription")}
            />
            <div className="flex gap-2">
              <Button
                size="icon"
                variant="secondary"
                aria-label={t("edit")}
                title={t("edit")}
                icon={<Edit className="h-5 w-5" />}
                onClick={() =>
                  navigate(`/dashboard/monitoring/${activeJob.id}/edit`)
                }
              />
              <Button
                size="icon"
                variant="secondary"
                aria-label={t("delete")}
                title={t("delete")}
                icon={<Trash2 className="h-5 w-5" />}
                onClick={() => setIsDeleteModalOpen(true)}
              />

              {isRunActive ? (
                <Button
                  size="md"
                  variant="danger"
                  onClick={handleCancelRun}
                  disabled={isCancelling}
                  className="flex items-center ml-2 gap-2"
                >
                  {isCancelling ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Square className="w-4 h-4 fill-current" />
                  )}
                  {isCancelling ? t("cancelling") : t("cancelRun")}
                </Button>
              ) : (
                <Button
                  size="md"
                  onClick={handleRunNow}
                  disabled={isRunning}
                  className="flex items-center ml-2 gap-2"
                >
                  {isRunning ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4" />
                  )}
                  {isRunning ? t("running") : t("run")}
                </Button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <CardSummary
              label={t("trigger")}
              value={formatNumber(activeJob.trigger_threshold, i18n.language)}
            />
            <CardSummary
              label={t("productionRecordsTotal")}
              value={formatNumber(productionCount, i18n.language)}
            />
            <CardSummary
              label={t("totalRuns")}
              value={formatNumber(totalRuns, i18n.language)}
            />
            <CardSummary
              label={t("driftDetectionRate")}
              value={`${formatNumber(driftRate, i18n.language, { maximumFractionDigits: 1 })}%`}
            />
          </div>

          <TerminalViewer
            key={effectiveRunId ?? "no-run"}
            title={t("console")}
            badge={statusBadge}
            logs={
              stream.error
                ? [...stream.logs, `Error: ${stream.error}`]
                : stream.logs
            }
            placeholder={t("noRuns")}
          />
        </div>

        <div className="border-t border-border pt-6 space-y-4">
          <StepTitle
            title={t("history")}
            description={t("historyDescription")}
          />
          <Table
            data={results ?? []}
            columns={columns}
            getRowId={(result) => result.id}
            loading={isLoadingResults}
            pageSize={5}
            emptyMessage={t("noRuns")}
          />
        </div>
      </PageBody>

      <ConfirmDialog
        open={isDeleteModalOpen}
        title={t("deleteTitle")}
        description={t("deleteDescription")}
        confirmText={t("deleteConfirm")}
        tone="danger"
        loading={isDeletingJob}
        onConfirm={() => {
          deleteJob(
            {
              id: activeJob.id,
              project_id: projectIdForJob ?? activeJob.project_id,
            },
            {
              onSuccess: () => {
                setIsDeleteModalOpen(false);
                handleBack();
              },
            },
          );
        }}
        onCancel={() => setIsDeleteModalOpen(false)}
      />

      <ConfirmDialog
        open={Boolean(runToDelete)}
        title={t("deleteRunTitle")}
        description={t("deleteRunDescription")}
        confirmText={t("deleteConfirm")}
        tone="danger"
        loading={isDeletingRun}
        onConfirm={() => {
          if (runToDelete) {
            deleteRun(runToDelete.id, {
              onSuccess: () => {
                setRunToDelete(null);
                if (activeRunId === runToDelete.id) {
                  setActiveRunId(null);
                }
              },
            });
          }
        }}
        onCancel={() => {
          if (!isDeletingRun) setRunToDelete(null);
        }}
      />
    </div>
  );
}
