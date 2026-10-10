import { RouteFallback } from "@/app/router/RouteFallback";
import { getProjectVersions } from "@/features/deployments/api/deployApi";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import {
  useDeleteDriftMonitoringJob,
  useDriftMonitoringJobs,
  useRunDriftMonitoringJob,
  type DriftMonitoringJob,
} from "@/features/monitoring/hooks/useDriftMonitoring";
import { NoProjectPlaceholder } from "@/features/projects/components/NoProjectPlaceholder";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { Select, type SelectOption } from "@/shared/components/Select";
import { Table } from "@/shared/components/Table";
import { formatDateTime } from "@/shared/i18n/formatters";
import { useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Edit, LineChart, Play, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate, useParams } from "react-router-dom";

export default function DriftMonitoringPage() {
  const { t, i18n } = useTranslation("monitoring");
  const { t: tCommon } = useTranslation("common");
  const { t: tProjects } = useTranslation("projects");
  const { modelId } = useParams<{ modelId: string }>();
  const { selectedModel, loading: isModelLoading } = useModelSelection();
  const navigate = useNavigate();

  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [jobToDelete, setJobToDelete] = useState<DriftMonitoringJob | null>(null);
  const [runningJobId, setRunningJobId] = useState<string | null>(null);

  const {
    data: jobs,
    isLoading: isLoadingJobs,
    error: jobsError,
  } = useDriftMonitoringJobs(modelId);

  const { data: projectVersions } = useQuery({
    queryKey: evolutionQueryKeys.versions(modelId ?? ""),
    queryFn: () => getProjectVersions(modelId!),
    enabled: Boolean(modelId),
  });

  const {
    mutate: deleteJob,
    isPending: isDeleting,
    error: deleteError,
    reset: resetDelete,
  } = useDeleteDriftMonitoringJob();

  const { mutate: runJob } = useRunDriftMonitoringJob();

  const versionMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const v of projectVersions ?? []) {
      const vNum = v.version.startsWith("v") ? v.version : `v${v.version}`;
      map.set(v.id, vNum);
    }
    return map;
  }, [projectVersions]);

  const getMonitorTypeLabel = (name: string) => {
    if (name === "default" || name === "data_drift") {
      return t("monitorTypes.dataDrift");
    }
    if (name === "target_drift") {
      return t("monitorTypes.targetDrift");
    }
    if (name === "concept_drift") {
      return t("monitorTypes.conceptDrift");
    }
    return name;
  };

  const typeOptions = useMemo<SelectOption[]>(
    () => [
      { value: "all", label: t("monitorTypes.all") },
      { value: "data_drift", label: t("monitorTypes.dataDrift") },
      { value: "target_drift", label: t("monitorTypes.targetDrift") },
      { value: "concept_drift", label: t("monitorTypes.conceptDrift") },
    ],
    [t],
  );

  const filteredJobs = useMemo(() => {
    const list = jobs ?? [];
    if (typeFilter === "all") return list;
    if (typeFilter === "data_drift") {
      return list.filter(
        (job) => job.name === "default" || job.name === "data_drift",
      );
    }
    return list.filter((job) => job.name === typeFilter);
  }, [jobs, typeFilter]);

  const handleRun = (job: DriftMonitoringJob) => {
    if (!modelId) return;
    setRunningJobId(job.id);
    runJob(
      { id: job.id, project_id: modelId },
      {
        onSettled: () => setRunningJobId(null),
      },
    );
  };

  const confirmDelete = () => {
    if (!jobToDelete || !modelId || isDeleting) return;
    deleteJob(
      { id: jobToDelete.id, project_id: modelId },
      {
        onSuccess: () => setJobToDelete(null),
      },
    );
  };

  const columns: ColumnDef<DriftMonitoringJob>[] = [
    {
      accessorKey: "id",
      header: t("driftJobId"),
      cell: ({ row }) => (
        <button
          type="button"
          className="text-color-primary hover:underline"
          onClick={() =>
            navigate(
              `/dashboard/projects/${modelId}/monitoring/${row.original.id}`,
            )
          }
        >
          {row.original.id}
        </button>
      ),
    },
    {
      accessorKey: "version_id",
      header: t("modelVersion"),
      cell: ({ row }) => {
        const displayVersion =
          versionMap.get(row.original.version_id) ??
          `v${row.original.version_id.slice(0, 8)}`;
        return (
          <span className="font-mono text-style-body font-medium">
            {displayVersion}
          </span>
        );
      },
    },
    {
      id: "monitor_type",
      header: t("monitorType"),
      cell: ({ row }) => (
        <span className="text-style-body">
          {getMonitorTypeLabel(row.original.name)}
        </span>
      ),
    },
    {
      accessorKey: "created_at",
      header: t("createdAt"),
      cell: ({ row }) => (
        <span className="whitespace-nowrap text-color-muted-foreground">
          {formatDateTime(row.original.created_at, i18n.language)}
        </span>
      ),
    },
    {
      accessorKey: "is_active",
      header: t("status"),
      cell: ({ row }) => (
        <Badge variant={row.original.is_active ? "success" : "neutral"}>
          {row.original.is_active ? t("active") : t("archived")}
        </Badge>
      ),
    },
    {
      id: "actions",
      header: t("actionsHeader"),
      enableSorting: false,
      cell: ({ row }) => {
        const job = row.original;
        const isRunningThis = runningJobId === job.id;
        return (
          <div className="flex flex-wrap items-center gap-1">
            <Button
              size="icon"
              variant="secondary"
              border={false}
              loading={isRunningThis}
              disabled={isRunningThis || isDeleting}
              icon={<Play className="h-4 w-4" />}
              title={t("actionTooltips.run")}
              aria-label={t("actionTooltips.run")}
              onClick={() => handleRun(job)}
            />
            <Button
              size="icon"
              variant="secondary"
              border={false}
              disabled={isDeleting}
              icon={<Edit className="h-4 w-4" />}
              title={t("actionTooltips.edit")}
              aria-label={t("actionTooltips.edit")}
              onClick={() => navigate(`/dashboard/monitoring/${job.id}/edit`)}
            />
            <Button
              size="icon"
              variant="danger"
              border={false}
              disabled={isDeleting}
              icon={<Trash2 className="h-4 w-4" />}
              title={t("actionTooltips.delete")}
              aria-label={t("actionTooltips.delete")}
              onClick={() => {
                resetDelete();
                setJobToDelete(job);
              }}
            />
          </div>
        );
      },
    },
  ];

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

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="w-full sm:w-60">
          <Select
            className="h-10 text-style-body"
            value={typeFilter}
            onChange={setTypeFilter}
            options={typeOptions}
            placeholder={t("filterMonitorType")}
          />
        </div>
        <Button
          size="md"
          icon={<Plus className="h-4 w-4" />}
          onClick={() =>
            navigate(`/dashboard/monitoring/new?projectId=${modelId}`)
          }
        >
          {t("createDriftMonitor")}
        </Button>
      </div>

      {Boolean(jobsError) && (
        <p role="alert" className="text-color-danger">
          {getApiErrorMessage(jobsError, t("failed"))}
        </p>
      )}

      <Table
        columns={columns}
        data={filteredJobs}
        loading={isLoadingJobs}
        emptyMessage={t("noMonitors")}
      />

      <ConfirmDialog
        open={Boolean(jobToDelete)}
        title={t("deleteTitle")}
        description={
          <div className="space-y-3">
            <p>{t("deleteDescription")}</p>
            {Boolean(deleteError) && (
              <p role="alert" className="text-color-danger">
                {getApiErrorMessage(deleteError, t("failed"))}
              </p>
            )}
          </div>
        }
        confirmText={t("deleteConfirm")}
        tone="danger"
        loading={isDeleting}
        onConfirm={confirmDelete}
        onCancel={() => {
          if (!isDeleting) setJobToDelete(null);
        }}
      />
    </div>
  );
}
