import { RouteFallback } from "@/app/router/RouteFallback";
import { SnapshotMetadata } from "@/features/evolution/components/SnapshotMetadata";
import {
  useProjectOverview,
  useRunningVersion,
} from "@/features/overview/hooks/useProjectOverview";
import { NoProjectPlaceholder } from "@/features/projects/components/NoProjectPlaceholder";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { Select } from "@/shared/components/Select";
import { formatDateTime, formatNumber } from "@/shared/i18n/formatters";
import type { ColumnDef } from "@tanstack/react-table";
import {
  ExternalLink,
  LineChart,
  Loader2,
  Play,
  Settings,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

import {
  useDeleteDriftMonitoringJob,
  useDriftMonitoringJobs,
  useDriftMonitoringResults,
  useRunDriftMonitoringJob,
  type DriftMonitoringResult,
} from "@/features/monitoring/hooks/useDriftMonitoring";
import { Badge } from "@/shared/components/Badge";
import { ExecutionObservation } from "@/shared/components/ExecutionObservation";
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

const DRIFT_TERMINAL_STATUSES = [
  "completed",
  "failed",
  "cancelled",
  "skipped",
] as const;

export default function DriftMonitoringPage() {
  const { t, i18n } = useTranslation("monitoring");
  const { t: tCommon } = useTranslation("common");
  const { t: tProjects } = useTranslation("projects");
  const { modelId } = useParams<{ modelId: string }>();
  const { selectedModel, loading: isModelLoading } = useModelSelection();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const project = useProjectOverview(modelId);
  const version = useRunningVersion(project.data?.active_endpoint?.version_id);

  const { data: jobs, isLoading: isLoadingJobs } =
    useDriftMonitoringJobs(modelId);
  const activeJob =
    jobs?.find((job) => job.id === params.get("monitorId")) ??
    jobs?.find(
      (job) =>
        job.is_active &&
        job.version_id === project.data?.active_endpoint?.version_id,
    ) ??
    jobs?.[0];
  const latestCurrentRun = (jobs ?? [])
    .filter(
      (job) => job.version_id === project.data?.active_endpoint?.version_id,
    )
    .flatMap((job) => job.runs ?? [])
    .filter((run) => run.status === "completed")
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];

  const {
    data: results,
    isLoading: isLoadingResults,
    refetch: refetchResults,
  } = useDriftMonitoringResults(activeJob?.id);
  const { mutate: deleteJob, isPending: isDeleting } =
    useDeleteDriftMonitoringJob();
  const { mutateAsync: runJob, isPending: isRunning } =
    useRunDriftMonitoringJob();

  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const stream = useRuntimeLogStream({
    source: activeRunId ? { kind: "drift", id: activeRunId } : null,
    enabled: Boolean(activeRunId),
    terminalStatuses: DRIFT_TERMINAL_STATUSES,
  });

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
    if (!modelId || !activeJob) return;
    const run = await runJob({ id: activeJob.id, project_id: modelId });
    setActiveRunId(run.id);
  };

  const handleViewReport = (runId: string) => {
    navigate(`/dashboard/projects/${modelId}/monitoring/report/${runId}`);
  };

  if (!modelId) {
    if (isModelLoading) return <RouteFallback />;
    if (selectedModel) {
      return (
        <Navigate
          to={`/dashboard/projects/${selectedModel.id}/monitoring`}
          replace
        />
      );
    }
    return (
      <div className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader title={t("title")} />
        <NoProjectPlaceholder
          title={tCommon("navigation.driftMonitoring")}
          description={tProjects("workflow.noProjectMonitoring")}
          icon={<LineChart className="h-6 w-6" />}
        />
      </div>
    );
  }

  if (isLoadingJobs) {
    return <div className="p-8">{t("loading")}</div>;
  }

  if (!activeJob) {
    return (
      <div className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader title={t("title")} />
        {version.data && <SnapshotMetadata version={version.data} />}
        <Placeholder
          title={t("title")}
          description={t("notConfigured")}
          icon={<LineChart className="h-6 w-6" />}
          action={
            <Button
              size="md"
              onClick={() => navigate(`/dashboard/monitoring/new`)}
            >
              {t("createMonitoring")}
            </Button>
          }
        />
      </div>
    );
  }

  const columns: ColumnDef<DriftMonitoringResult>[] = [
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
      id: "action",
      header: t("report"),
      enableSorting: false,
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          icon={<ExternalLink className="h-4 w-4" />}
          disabled={
            row.original.status !== "completed" || !row.original.report_html_uri
          }
          onClick={() => handleViewReport(row.original.id)}
        >
          {t("viewReport")}
        </Button>
      ),
    },
  ];

  return (
    <div className="flex w-full flex-1 flex-col space-y-6">
      <PageHeader title={t("title")} />
      <ExecutionObservation state={results?.find((run) => run.id === activeRunId) ?? results?.[0]} />
      <p className="text-color-muted-foreground">{t("runningDriftOnly")}</p>
      <section className="rounded-surface border border-border bg-surface p-4 space-y-2">
        <h2>{t("currentStatus")}</h2>
        {latestCurrentRun ? (
          <Badge variant={latestCurrentRun.has_drift ? "danger" : "success"}>
            {latestCurrentRun.has_drift ? t("driftDetected") : t("healthy")}
          </Badge>
        ) : (
          <p>{t("noCurrentResult")}</p>
        )}
      </section>
      {version.data && <SnapshotMetadata version={version.data} />}
      <Button
        variant="secondary"
        onClick={() =>
          navigate(`/dashboard/monitoring/new?projectId=${modelId}`)
        }
        disabled={!project.data?.active_endpoint}
      >
        {t("createMonitoring")}
      </Button>
      <Select
        value={activeJob.id}
        onChange={(monitorId) => {
          setParams({ monitorId });
          setActiveRunId(null);
        }}
        options={(jobs ?? []).map((job) => ({
          value: job.id,
          label: `${job.name} · ${job.version_id} · ${job.is_active ? t("active") : t("archived")}`,
        }))}
      />

      <PageBody className="p-6 space-y-6">
        <div className="flex flex-col space-y-4">
          <div className="flex justify-between items-start">
            <StepTitle title={t("configuration")} />
            <div className="flex gap-2">
              <Button
                size="icon"
                variant="ghost"
                aria-label={t("edit")}
                title={t("edit")}
                icon={<Settings className="h-5 w-5" />}
                onClick={() =>
                  navigate(`/dashboard/monitoring/${activeJob.id}/edit`)
                }
              />
              <Button
                size="icon"
                aria-label={t("delete")}
                title={t("delete")}
                variant="danger-outline"
                icon={<Trash2 className="h-5 w-5" />}
                onClick={() => setIsDeleteModalOpen(true)}
              />

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
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <CardSummary
              label={t("trigger")}
              value={activeJob.trigger_threshold.toString()}
            />
            <CardSummary
              label={t("referencePath")}
              value={activeJob.reference_name || t("none")}
            />
          </div>
        </div>

        <div className="border-t border-border pt-6 space-y-4">
          {activeRunId && (
            <TerminalViewer
              key={activeRunId}
              title={t("console")}
              logs={
                stream.error
                  ? [...stream.logs, `Error: ${stream.error}`]
                  : stream.logs
              }
            />
          )}
          <StepTitle title={t("history")} />
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
        loading={isDeleting}
        onConfirm={() => {
          deleteJob({ id: activeJob.id, project_id: modelId! });
          setIsDeleteModalOpen(false);
        }}
        onCancel={() => setIsDeleteModalOpen(false)}
      />
    </div>
  );
}
