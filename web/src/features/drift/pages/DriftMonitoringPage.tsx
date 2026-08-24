import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Play,
  Settings,
  Trash2,
  ExternalLink,
  LineChart,
  Loader2,
} from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import { useTranslation } from "react-i18next";

import { Placeholder } from "@/shared/components/Placeholder";
import { PageHeader } from "@/shared/components/PageHeader";
import { PageBody } from "@/shared/components/PageBody";
import { StepTitle } from "@/shared/components/StepTitle";
import { CardSummary } from "@/shared/components/Card";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { TerminalViewer } from "@/shared/components/TerminalViewer";
import { DataTable } from "@/shared/components/DataTable";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import {
  useDriftMonitoringJobs,
  useDriftMonitoringResults,
  useDeleteDriftMonitoringJob,
  useRunDriftMonitoringJob,
  type DriftMonitoringResult,
} from "@/features/drift/hooks/useDriftMonitoring";

const DRIFT_TERMINAL_STATUSES = ["completed", "failed", "cancelled"] as const;

export default function DriftMonitoringPage() {
  const { t, i18n } = useTranslation("drift");
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();

  const { data: jobs, isLoading: isLoadingJobs } =
    useDriftMonitoringJobs(modelId);
  const activeJob = jobs?.find((job) => job.is_active);

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
    navigate(`/dashboard/drift-monitoring/${modelId}/report/${runId}`);
  };

  if (isLoadingJobs) {
    return <div className="p-8">{t("loading")}</div>;
  }

  if (!activeJob) {
    return (
      <div className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader title={t("title")} />
        <Placeholder
          title={t("title")}
          description={t("notConfigured")}
          icon={<LineChart className="h-6 w-6" />}
          action={
            <Button
              size="md"
              onClick={() =>
                navigate(`/dashboard/drift-monitoring/${modelId}/new`)
              }
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
          {new Date(row.original.created_at).toLocaleString(i18n.language)}
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
            : `${(row.original.drift_score * 100).toFixed(1)}%`}
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
          disabled={!row.original.report_html_uri}
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
                  navigate(`/dashboard/drift-monitoring/${modelId}/edit`)
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
              value={activeJob.reference_asset_name || t("none")}
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
          <DataTable
            data={results ?? []}
            columns={columns}
            getRowId={(result) => result.id}
            loading={isLoadingResults}
            pageSize={5}
            emptyMessage={t("noRuns")}
          />
        </div>
      </PageBody>

      <ConfirmModal
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
