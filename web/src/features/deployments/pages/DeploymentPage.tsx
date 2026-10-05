import { RouteFallback } from "@/app/router/RouteFallback";
import {
  buildDeploymentPath,
  runDeploymentPath,
} from "@/features/deployments/navigation";
import { isDeployableBuild } from "@/features/deployments/deploymentEligibility";
import {
  canDeleteBuild,
  canRebuild,
} from "@/features/deployments/buildActions";
import {
  buildStatuses,
  deploymentStatuses,
  getBuildDeploymentStatus,
  matchesBuildStatus,
  registrationStatuses,
} from "@/features/deployments/buildHistoryStatus";
import { useBuildActions } from "@/features/deployments/hooks/useBuildActions";
import {
  useBuildHistory,
  useDeployments,
} from "@/features/deployments/hooks/useDeploymentFlow";
import { useProjectOverview } from "@/features/overview/hooks/useProjectOverview";
import { NoProjectPlaceholder } from "@/features/projects/components/NoProjectPlaceholder";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import type { Build } from "@/features/projects/types";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { PageHeader } from "@/shared/components/PageHeader";
import { Select, type SelectOption } from "@/shared/components/Select";
import { Table } from "@/shared/components/Table";
import { formatDateTime } from "@/shared/i18n/formatters";
import type { ColumnDef } from "@tanstack/react-table";
import { Box, Play, RotateCcw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate, useParams } from "react-router-dom";

export default function DeploymentPage() {
  const { modelId } = useParams();
  const { t, i18n } = useTranslation("projects");
  const { t: tCommon } = useTranslation("common");
  const { selectedModel, loading: isModelLoading } = useModelSelection();
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const builds = useBuildHistory(modelId);
  const deployments = useDeployments();
  const project = useProjectOverview(modelId);
  const { rebuild, remove } = useBuildActions(modelId);
  const [action, setAction] = useState<{
    kind: "rebuild" | "delete";
    build: Build;
  } | null>(null);
  const actionPending = rebuild.isPending || remove.isPending;
  const confirmAction = () => {
    if (!action || actionPending) return;
    if (action.kind === "delete") {
      remove.mutate(action.build.id, { onSuccess: () => setAction(null) });
    } else {
      rebuild.mutate(action.build.id, {
        onSuccess: (build) => {
          setAction(null);
          navigate(
            buildDeploymentPath({
              projectId: build.project_id,
              buildId: build.id,
            }),
          );
        },
      });
    }
  };
  const columns: ColumnDef<Build>[] = [
    {
      accessorKey: "id",
      header: t("workflow.buildId"),
      cell: ({ row }) => (
        <button
          type="button"
          className="text-color-primary"
          onClick={() =>
            navigate(
              buildDeploymentPath({
                projectId: row.original.project_id,
                buildId: row.original.id,
              }),
            )
          }
        >
          {row.original.id}
        </button>
      ),
    },
    {
      accessorKey: "created_at",
      header: t("workflow.builtAt"),
      cell: ({ row }) => formatDateTime(row.original.created_at, i18n.language),
    },
    {
      id: "source",
      header: t("workflow.sourceType"),
      cell: ({ row }) =>
        t(row.original.source_job_id ? "workflow.trained" : "workflow.preview"),
    },
    {
      accessorKey: "status",
      header: t("workflow.buildStatus"),
      cell: ({ row }) => {
        const status = buildStatuses[row.original.status];
        return <Badge variant={status.tone}>{t(status.label)}</Badge>;
      },
    },
    {
      accessorKey: "registration_status",
      header: t("workflow.registrationStatus"),
      cell: ({ row }) => {
        const status = registrationStatuses[row.original.registration_status];
        return <Badge variant={status.tone}>{t(status.label)}</Badge>;
      },
    },
    {
      id: "deployment_status",
      header: t("workflow.deploymentStatus"),
      accessorFn: (build) =>
        deployments.data
          ? getBuildDeploymentStatus(build.id, deployments.data)
          : undefined,
      cell: ({ row }) => {
        if (deployments.isError) {
          return (
            <Badge variant="warning">
              {t("workflow.deploymentStatusUnavailable")}
            </Badge>
          );
        }
        if (!deployments.data) {
          return <Badge>{t("workflow.loading")}</Badge>;
        }
        const status =
          deploymentStatuses[
            getBuildDeploymentStatus(row.original.id, deployments.data)
          ];
        return <Badge variant={status.tone}>{t(status.label)}</Badge>;
      },
    },
    {
      id: "actions",
      header: t("workflow.actions"),
      enableSorting: false,
      cell: ({ row }) => {
        const build = row.original;
        const registered =
          Boolean(build.version_id) ||
          ["registering", "registered"].includes(build.registration_status);
        return (
          <div className="flex flex-wrap items-center gap-1">
            {isDeployableBuild(build, build.project_id) && (
              <Button
                size="icon"
                variant="secondary"
                border={false}
                icon={<Play className="h-4 w-4" />}
                title={t("workflow.openRunDeployment")}
                aria-label={t("workflow.openRunDeployment")}
                onClick={() =>
                  navigate(runDeploymentPath(build.project_id, build.id))
                }
              />
            )}
            <Button
              size="icon"
              variant="secondary"
              border={false}
              icon={<RotateCcw className="h-4 w-4" />}
              disabled={actionPending || !canRebuild(build)}
              title={t("workflow.rebuild")}
              aria-label={t("workflow.rebuildLabel", { id: build.id })}
              onClick={() => {
                rebuild.reset();
                remove.reset();
                setAction({ kind: "rebuild", build });
              }}
            />
            <Button
              size="icon"
              variant="danger"
              border={false}
              icon={<Trash2 className="h-4 w-4" />}
              loading={build.deletion_state === "deleting"}
              disabled={actionPending || !canDeleteBuild(build)}
              title={
                registered
                  ? t("workflow.registeredBuildProtected")
                  : t("workflow.deleteBuild")
              }
              aria-label={t("workflow.deleteBuildLabel", { id: build.id })}
              onClick={() => {
                rebuild.reset();
                remove.reset();
                setAction({ kind: "delete", build });
              }}
            />
            {build.deletion_state === "deleting" && (
              <Badge variant="warning">{t("workflow.deletingBuild")}</Badge>
            )}
            {build.deletion_state === "delete_failed" && (
              <Badge variant="danger">{t("workflow.deleteBuildFailed")}</Badge>
            )}
          </div>
        );
      },
    },
  ];

  const statusOptions = useMemo<SelectOption[]>(
    () => [
      { value: "all", label: t("workflow.allBuildStatuses") },
      ...Object.entries(buildStatuses).map(([value, status]) => ({
        value,
        label: t(status.label),
      })),
    ],
    [t],
  );

  const filteredBuilds = useMemo(() => {
    const list = builds.data ?? [];
    return list.filter((build) => matchesBuildStatus(build, statusFilter));
  }, [builds.data, statusFilter]);

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
      <div className="flex w-full flex-1 flex-col space-y-6">
        <PageHeader title={t("workflow.deployment")} />
        <NoProjectPlaceholder
          title={tCommon("navigation.deployment")}
          description={t("workflow.noProjectDeployment")}
          icon={<Box className="h-6 w-6" />}
        />
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <PageHeader title={t("workflow.deployment")} />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="w-full sm:w-60">
          <Select
            className="h-10 text-style-body"
            value={statusFilter}
            onChange={setStatusFilter}
            options={statusOptions}
            placeholder={t("workflow.filterBuildStatus")}
          />
        </div>
        <Button
          size="md"
          icon={<Play className="h-4 w-4" />}
          onClick={() => navigate(buildDeploymentPath({ projectId: modelId }))}
        >
          {t("workflow.deploy")}
        </Button>
      </div>

      {(builds.error || project.error) && (
        <p role="alert">
          {getApiErrorMessage(
            builds.error || project.error,
            t("workflow.failed"),
          )}
        </p>
      )}
      <Table
        columns={columns}
        data={filteredBuilds}
        loading={builds.isLoading}
      />
      {Boolean(rebuild.error || remove.error) && !action && (
        <p role="alert" className="text-color-danger">
          {getApiErrorMessage(
            rebuild.error || remove.error,
            t("workflow.buildActionFailed"),
          )}
        </p>
      )}
      <ConfirmDialog
        open={Boolean(action)}
        title={t(
          action?.kind === "delete"
            ? "workflow.deleteBuildTitle"
            : "workflow.rebuildTitle",
        )}
        description={
          <div className="space-y-3">
            <p>
              {t(
                action?.kind === "delete"
                  ? "workflow.deleteBuildDescription"
                  : "workflow.rebuildDescription",
                { id: action?.build.id },
              )}
            </p>
            {Boolean(rebuild.error || remove.error) && (
              <p role="alert" className="text-color-danger">
                {getApiErrorMessage(
                  rebuild.error || remove.error,
                  t("workflow.buildActionFailed"),
                )}
              </p>
            )}
          </div>
        }
        confirmText={
          action?.kind === "delete"
            ? t("workflow.deleteBuild")
            : t("workflow.rebuild")
        }
        tone={action?.kind === "delete" ? "danger" : "default"}
        loading={actionPending}
        onConfirm={confirmAction}
        onCancel={() => {
          if (!actionPending) setAction(null);
        }}
      />
    </div>
  );
}
