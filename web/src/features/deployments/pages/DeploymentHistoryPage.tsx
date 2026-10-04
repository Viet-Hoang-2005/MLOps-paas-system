import { Navigate, useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import type { Build } from "@/features/projects/types";
import {
  useBuildHistory,
  useDeployments,
} from "@/features/deployments/hooks/useDeploymentFlow";
import { PageHeader } from "@/shared/components/PageHeader";
import { DataTable } from "@/shared/components/DataTable";
import { Button } from "@/shared/components/Button";
import { RouteFallback } from "@/app/router/RouteFallback";
import { useProjectOverview } from "@/features/projects/hooks/useProjectOverview";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { NoProjectPlaceholder } from "@/features/projects/components/NoProjectPlaceholder";
import { getApiErrorMessage } from "@/shared/api/errors";

export default function DeploymentHistoryPage() {
  const { modelId } = useParams();
  const { t } = useTranslation("projects");
  const { t: tCommon } = useTranslation("common");
  const { selectedModel, loading: isModelLoading } = useModelSelection();
  const navigate = useNavigate();
  const builds = useBuildHistory(modelId);
  const deployments = useDeployments();
  const project = useProjectOverview(modelId);
  const columns: ColumnDef<Build>[] = [
    {
      accessorKey: "id",
      header: t("workflow.buildId"),
      cell: ({ row }) => (
        <button
          type="button"
          className="text-color-primary"
          onClick={() =>
            navigate(`/dashboard/deployments/new?buildId=${row.original.id}`)
          }
        >
          {row.original.id}
        </button>
      ),
    },
    {
      accessorKey: "created_at",
      header: t("workflow.builtAt"),
      cell: ({ row }) => new Date(row.original.created_at).toLocaleString(),
    },
    {
      id: "project",
      header: t("workflow.name"),
      cell: () => project.data?.name || "—",
    },
    {
      id: "source",
      header: t("workflow.sourceType"),
      cell: ({ row }) =>
        t(row.original.source_job_id ? "workflow.trained" : "workflow.preview"),
    },
    { accessorKey: "flavor", header: t("flavor") },
    { accessorKey: "version_number", header: t("workflow.version") },
    {
      accessorKey: "status",
      header: t("workflow.status"),
      cell: ({ row }) => {
        const build = row.original;
        const deployment = deployments.data?.find(
          (item) => item.build_id === build.id,
        );
        if (
          deployment?.status === "deploying" ||
          deployment?.status === "pending"
        )
          return t("workflow.deploying");
        if (
          deployment?.status === "failed" ||
          deployment?.status === "unhealthy"
        )
          return t("workflow.deployFailed");
        return build.status === "ready"
          ? t(
              deployment?.status === "healthy" || deployment?.deployed_at
                ? "workflow.buildDeployed"
                : "workflow.buildOnly",
            )
          : t(`workflow.${build.status}`);
      },
    },
  ];
  if (!modelId) {
    if (isModelLoading) return <RouteFallback />;
    if (selectedModel) {
      return (
        <Navigate
          to={`/dashboard/projects/${selectedModel.id}/deployment`}
          replace
        />
      );
    }
    return (
      <NoProjectPlaceholder
        title={tCommon("navigation.deployment")}
        description={t("workflow.noProjectDeployment")}
        icon={<Bot className="h-6 w-6" />}
      />
    );
  }
  return (
    <div className="space-y-6">
      <PageHeader
        title={t("workflow.deployment")}
        actions={
          <Button
            onClick={() =>
              navigate(
                `/dashboard/deployments/new${modelId ? `?projectId=${modelId}` : ""}`,
              )
            }
          >
            {t("workflow.deploy")}
          </Button>
        }
      />
      {(builds.error || project.error) && (
        <p role="alert">
          {getApiErrorMessage(
            builds.error || project.error,
            t("workflow.failed"),
          )}
        </p>
      )}
      <DataTable
        columns={columns}
        data={builds.data ?? []}
        loading={builds.isLoading}
      />
    </div>
  );
}
