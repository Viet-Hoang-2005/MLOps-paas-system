import { useDriftReportData } from "@/features/monitoring/hooks/useDriftMonitoring";
import { DriftDistributionModal } from "@/features/monitoring/components/DriftDistributionModal";
import type { DriftColumnReport } from "@/features/monitoring/types";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { CardSummary } from "@/shared/components/Card";
import { PageHeader } from "@/shared/components/PageHeader";
import { Search } from "@/shared/components/Search";
import { Select } from "@/shared/components/Select";
import { Table } from "@/shared/components/Table";
import { formatNumber } from "@/shared/i18n/formatters";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Activity,
  Columns3,
  Database,
  Download,
  Eye,
  Gauge,
  Loader2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

export default function DriftReportPage() {
  const { runId } = useParams<{ modelId: string; runId: string }>();
  const { t, i18n } = useTranslation("monitoring");

  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [selectedColumn, setSelectedColumn] =
    useState<DriftColumnReport | null>(null);

  const { data, isLoading, error } = useDriftReportData(runId);

  const handleDownloadFile = async (
    fileUrl: string | null | undefined,
    fileName: string,
  ) => {
    if (!fileUrl) return;
    try {
      const response = await fetch(fileUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      window.open(fileUrl, "_blank");
    }
  };

  const columnsList = data?.columns;

  const filteredColumns = useMemo(() => {
    if (!columnsList) return [];
    return columnsList.filter((col) => {
      if (
        searchTerm &&
        !col.column_name.toLowerCase().includes(searchTerm.toLowerCase().trim())
      ) {
        return false;
      }
      if (statusFilter === "drifted" && !col.drift_detected) return false;
      if (statusFilter === "healthy" && col.drift_detected) return false;
      if (typeFilter === "num" && col.column_type !== "num") return false;
      if (typeFilter === "cat" && col.column_type !== "cat") return false;
      return true;
    });
  }, [columnsList, searchTerm, statusFilter, typeFilter]);

  const numCount =
    data?.columns.filter((c) => c.column_type === "num").length ?? 0;
  const catCount =
    data?.columns.filter((c) => c.column_type === "cat").length ?? 0;

  const columns: ColumnDef<DriftColumnReport>[] = useMemo(
    () => [
      {
        accessorKey: "column_name",
        header: t("reportPage.columns.featureName"),
        cell: ({ row }) => (
          <span className="text-style-body-strong text-color-foreground">
            {row.original.column_name}
          </span>
        ),
      },
      {
        accessorKey: "column_type",
        header: t("reportPage.columns.type"),
        cell: ({ row }) => (
          <Badge variant="neutral" hideIcon={true} border={true} size="sm">
            {row.original.column_type === "num"
              ? t("reportPage.numerical")
              : t("reportPage.categorical")}
          </Badge>
        ),
      },
      {
        accessorKey: "stattest_name",
        header: t("reportPage.columns.statTest"),
        cell: ({ row }) => (
          <span className="text-style-body text-color-foreground">
            {row.original.stattest_name}
          </span>
        ),
      },
      {
        accessorKey: "stattest_threshold",
        header: t("reportPage.columns.threshold"),
        cell: ({ row }) => (
          <span className="text-style-code-sm text-color-foreground">
            {row.original.stattest_threshold.toFixed(2)}
          </span>
        ),
      },
      {
        accessorKey: "drift_score",
        header: t("reportPage.columns.driftScore"),
        cell: ({ row }) => (
          <span className="text-style-code-sm text-color-foreground font-semibold">
            {row.original.drift_score.toFixed(4)}
          </span>
        ),
      },
      {
        accessorKey: "drift_detected",
        header: t("reportPage.columns.status"),
        cell: ({ row }) => (
          <Badge variant={row.original.drift_detected ? "danger" : "success"}>
            {row.original.drift_detected
              ? t("reportPage.driftDetected")
              : t("reportPage.noDrift")}
          </Badge>
        ),
      },
      {
        id: "actions",
        header: t("reportPage.columns.actions"),
        enableSorting: false,
        cell: ({ row }) => (
          <Button
            size="sm"
            variant="secondary"
            icon={<Eye className="h-4 w-4" />}
            onClick={() => setSelectedColumn(row.original)}
          >
            {t("reportPage.viewDistribution")}
          </Button>
        ),
      },
    ],
    [t],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("reportPage.title")}
        back
      >
      </PageHeader>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-24 text-color-muted-foreground">
          <Loader2 className="w-8 h-8 animate-spin mb-3" />
          <p className="text-style-body">{t("reportPage.loading")}</p>
        </div>
      ) : error || !data ? (
        <div className="rounded-surface border border-border bg-surface p-8 text-center text-color-danger">
          {t("reportPage.loadFailed")}
        </div>
      ) : (
        <>
          {/* Top 4 KPI Summary Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <CardSummary
              label={t("reportPage.datasetDrift")}
              tone={data.dataset_drift ? "error" : "success"}
              icon={<Activity className="h-5 w-5" />}
              value={
                <span
                  className={
                    data.dataset_drift
                      ? "text-color-danger"
                      : "text-color-success"
                  }
                >
                  {data.dataset_drift
                    ? t("reportPage.driftDetected")
                    : t("reportPage.noDrift")}
                </span>
              }
              helper={`${data.number_of_drifted_columns} / ${data.number_of_columns} ${t("reportPage.driftedFeatures").toLowerCase()}`}
            />

            <CardSummary
              label={t("reportPage.driftScore")}
              tone={data.dataset_drift ? "warning" : "default"}
              icon={<Gauge className="h-5 w-5" />}
              value={`${(data.drift_score * 100).toFixed(1)}%`}
              helper={`${t("reportPage.threshold")}: ${(data.drift_share * 100).toFixed(0)}%`}
            />

            <CardSummary
              label={t("reportPage.featuresBreakdown")}
              icon={<Columns3 className="h-5 w-5" />}
              value={data.number_of_columns}
              helper={`${numCount} ${t("reportPage.numerical").toLowerCase()} • ${catCount} ${t("reportPage.categorical").toLowerCase()}`}
            />

            <CardSummary
              label={t("reportPage.sampleSizes")}
              tone="info"
              icon={<Database className="h-5 w-5" />}
              value={formatNumber(data.production_records, i18n.language)}
              helper={`${t("reportPage.dataQuality")}: ${data.data_quality?.status === "healthy" ? t("reportPage.schemaHealthy") : "Alert"}`}
            />
          </div>

          {/* Filter toolbar & Features Table */}
          <div className="space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap gap-3">
                <div className="w-full sm:w-40">
                  <Select
                    className="h-10 text-style-body"
                    value={typeFilter}
                    onChange={setTypeFilter}
                    options={[
                      { value: "all", label: t("reportPage.allTypes") },
                      { value: "num", label: t("reportPage.numerical") },
                      { value: "cat", label: t("reportPage.categorical") },
                    ]}
                    placeholder={t("reportPage.filterType")}
                  />
                </div>
                <div className="w-full sm:w-40">
                  <Select
                    className="h-10 text-style-body"
                    value={statusFilter}
                    onChange={setStatusFilter}
                    options={[
                      { value: "all", label: t("reportPage.allStatuses") },
                      {
                        value: "drifted",
                        label: t("reportPage.driftedOnly"),
                      },
                      {
                        value: "healthy",
                        label: t("reportPage.healthyOnly"),
                      },
                    ]}
                    placeholder={t("reportPage.filterStatus")}
                  />
                </div>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                <Search
                  wrapperClassName="w-full sm:w-72"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  onClear={() => setSearchTerm("")}
                  placeholder={t("reportPage.searchPlaceholder")}
                />

                {data?.artifacts?.html_url && (
                  <Button
                    size="md"
                    icon={<Download className="h-4 w-4" />}
                    onClick={() =>
                      handleDownloadFile(
                        data.artifacts.html_url,
                        `drift-report-${data.run_id}.html`,
                      )
                    }
                  >
                    {t("reportPage.downloadHtml")}
                  </Button>
                )}
              </div>
            </div>

            <Table
              data={filteredColumns}
              columns={columns}
              pageSize={15}
              emptyMessage={t("reportPage.noFeaturesFound")}
            />
          </div>

          {/* Modal for viewing distribution */}
          <DriftDistributionModal
            column={selectedColumn}
            onClose={() => setSelectedColumn(null)}
          />
        </>
      )}
    </div>
  );
}
