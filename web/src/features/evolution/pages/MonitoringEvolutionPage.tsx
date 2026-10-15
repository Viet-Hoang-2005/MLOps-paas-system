import {
  useDriftMonitoringJobs,
  useDriftMonitoringResults,
  type DriftMonitoringResult,
} from "@/features/monitoring/hooks/useDriftMonitoring";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { CardSummary } from "@/shared/components/Card";
import { Placeholder } from "@/shared/components/Placeholder";
import { Table } from "@/shared/components/Table";
import { Title } from "@/shared/components/Title";
import { formatDateTime, formatNumber } from "@/shared/i18n/formatters";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Eye,
  LineChart,
  Plus,
  TrendingUp,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export interface MonitoringEvolutionPageProps {
  projectId: string;
  versionId: string;
}

export function MonitoringEvolutionPage({
  projectId,
  versionId,
}: MonitoringEvolutionPageProps) {
  const { t, i18n } = useTranslation("evolution");
  const navigate = useNavigate();

  const { data: jobs, isLoading: isLoadingJobs } =
    useDriftMonitoringJobs(projectId);

  const activeJob =
    jobs?.find((j) => j.version_id === versionId) ??
    (jobs && jobs.length === 1 ? jobs[0] : undefined);

  const { data: results, isLoading: isLoadingResults } =
    useDriftMonitoringResults(activeJob?.id);

  const totalRuns = results?.length ?? 0;
  const driftDetectedRuns =
    results?.filter((run) => run.has_drift === true).length ?? 0;
  const healthyRuns =
    results?.filter((run) => run.status === "completed" && !run.has_drift)
      .length ?? 0;
  const driftRate = totalRuns > 0 ? (driftDetectedRuns / totalRuns) * 100 : 0;

  const handleViewReport = (runId: string) => {
    navigate(`/dashboard/projects/${projectId}/monitoring/report/${runId}`);
  };

  const columns: ColumnDef<DriftMonitoringResult>[] = [
    {
      accessorKey: "id",
      header: t("workspace.runId", "Run ID"),
      cell: ({ row }) => (
        <button
          type="button"
          className="text-color-primary font-mono hover:underline disabled:text-color-muted-foreground disabled:no-underline font-medium"
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
      header: t("workspace.runAt", "Run At"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap text-color-muted-foreground">
          {formatDateTime(row.original.created_at, i18n.language)}
        </span>
      ),
    },
    {
      id: "production_records",
      header: t("workspace.productionRecords", "Production Records"),
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
      header: t("workspace.driftScore", "Drift Score"),
      cell: ({ row }) => (
        <span className="font-mono font-semibold">
          {row.original.drift_score == null
            ? t("workspace.none", "None")
            : `${formatNumber(row.original.drift_score * 100, i18n.language, {
                minimumFractionDigits: 1,
                maximumFractionDigits: 1,
              })}%`}
        </span>
      ),
    },
    {
      id: "status",
      header: t("workspace.status", "Status"),
      cell: ({ row }) => {
        if (row.original.status !== "completed")
          return <Badge variant="neutral">{row.original.status}</Badge>;
        return (
          <Badge variant={row.original.has_drift ? "danger" : "success"}>
            {row.original.has_drift
              ? t("workspace.driftDetected", "Drift Detected")
              : t("workspace.noDrift", "Healthy")}
          </Badge>
        );
      },
    },
    {
      id: "actions",
      header: t("workspace.actionsHeader", "Actions"),
      enableSorting: false,
      cell: ({ row }) => (
        <Button
          size="sm"
          variant="secondary"
          icon={<Eye className="h-4 w-4" />}
          disabled={
            row.original.status !== "completed" || !row.original.report_html_uri
          }
          onClick={() => handleViewReport(row.original.id)}
        >
          {t("workspace.viewReport", "View Report")}
        </Button>
      ),
    },
  ];

  if (isLoadingJobs) {
    return (
      <div className="rounded-surface border border-border bg-surface p-12 text-center text-color-muted-foreground">
        {t("workspace.loading", "Loading...")}
      </div>
    );
  }

  if (!activeJob) {
    return (
      <Placeholder
        role="tabpanel"
        className="min-h-80"
        icon={<LineChart className="h-6 w-6 text-color-primary" />}
        title={t("workspace.noMonitoringJobTitle", "No Drift Monitor Configured")}
        description={t(
          "workspace.noMonitoringJobDesc",
          "There is no drift monitoring job configured for this model version yet.",
        )}
        action={
          <Button
            variant="secondary"
            icon={<Plus className="h-4 w-4" />}
            onClick={() =>
              navigate(`/dashboard/projects/${projectId}/monitoring/new`)
            }
          >
            {t("workspace.createMonitor", "Configure Drift Monitor")}
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <section className="space-y-4">
        <Title title={t("workspace.evidentlyRuns", "Evidently Drift Runs")} />

        {/* 4 CardSummary for Evidently Data Drift Job */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <CardSummary
            label={t("workspace.totalRuns", "Total Runs")}
            value={formatNumber(totalRuns, i18n.language)}
            icon={<Activity className="h-5 w-5" />}
          />
          <CardSummary
            label={t("workspace.driftDetectedCount", "Drift Detected")}
            value={formatNumber(driftDetectedRuns, i18n.language)}
            icon={<AlertTriangle className="h-5 w-5" />}
            tone={driftDetectedRuns > 0 ? "error" : "default"}
          />
          <CardSummary
            label={t("workspace.healthyCount", "Healthy")}
            value={formatNumber(healthyRuns, i18n.language)}
            icon={<CheckCircle2 className="h-5 w-5" />}
            tone={healthyRuns > 0 ? "success" : "default"}
          />
          <CardSummary
            label={t("workspace.driftDetectionRate", "Drift Detection Rate")}
            value={`${formatNumber(driftRate, i18n.language, { maximumFractionDigits: 1 })}%`}
            icon={<TrendingUp className="h-5 w-5" />}
            tone={driftRate > 0 ? "warning" : "default"}
          />
        </div>

        <Table
          columns={columns}
          data={results ?? []}
          loading={isLoadingResults}
          emptyMessage={t(
            "workspace.noRuns",
            "No drift monitoring runs recorded.",
          )}
        />
      </section>
    </div>
  );
}

export { MonitoringEvolutionPage as EvolutionMonitoringTab };
