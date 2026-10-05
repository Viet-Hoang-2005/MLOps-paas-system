import { RouteFallback } from "@/app/router/RouteFallback";
import { deploymentStatuses } from "@/features/deployments/buildHistoryStatus";
import { useRunDeployment } from "@/features/deployments/hooks/useRunDeployment";
import {
  buildDeploymentPath,
  runDeploymentPath,
} from "@/features/deployments/navigation";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { CardSummary } from "@/shared/components/Card";
import { PageHeader } from "@/shared/components/PageHeader";
import { TerminalViewer } from "@/shared/components/TerminalViewer";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { Play } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

export default function RunDeploymentPage() {
  const { projectId = "", buildId = "" } = useParams();
  return (
    <RunDeploymentContent
      key={`${projectId}:${buildId}`}
      projectId={projectId}
      buildId={buildId}
    />
  );
}

function RunDeploymentContent({
  projectId,
  buildId,
}: {
  projectId: string;
  buildId: string;
}) {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const run = useRunDeployment(projectId, buildId, params.get("deploymentId"));
  const logs = useRuntimeLogStream({
    source:
      run.eligible && !run.mismatch && run.selected
        ? { kind: "deployment", id: run.selected.id }
        : null,
    terminalStatuses: ["succeeded", "failed", "stopped", "unconfirmed"],
  });
  const attemptStatus =
    deploymentStatuses[run.selected?.status ?? "not_deployed"];
  const error = run.error || run.deploy.error;
  const isDeploySuccess = Boolean(
    run.running || run.selected?.status === "succeeded",
  );
  const modelLifecycleStatus = run.project.data?.lifecycle_status;
  const modelStatusTone =
    modelLifecycleStatus === "running"
      ? "success"
      : modelLifecycleStatus === "registered"
        ? "info"
        : "neutral";
  if (run.loading && !run.build.data) return <RouteFallback />;
  if (run.mismatch || run.error || (!run.loading && !run.eligible)) {
    return (
      <div className="space-y-6">
        <PageHeader title={t("workflow.runDeployment")} back />
        <Callout
          variant="danger"
          title={t("workflow.runNotEligible")}
          description={
            run.error
              ? getApiErrorMessage(run.error, t("workflow.notFound"))
              : run.mismatch
                ? t("workflow.invalidBuildProject")
                : t("workflow.registeredBuildRequired")
          }
        />
        <Button
          variant="secondary"
          onClick={() => navigate(buildDeploymentPath({ projectId, buildId }))}
        >
          {t("workflow.openBuild")}
        </Button>
      </div>
    );
  }
  return (
    <div className="flex min-h-full w-full flex-1 flex-col space-y-6">
      <PageHeader title={t("workflow.runDeployment")} back />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <CardSummary
          label={t("workflow.modelName")}
          value={run.project.data?.name || "-"}
        />
        <CardSummary
          label={t("workflow.frameworkFlavor")}
          value={run.build.data?.flavor || run.project.data?.flavor || "-"}
        />
        <CardSummary
          label={t("workflow.modelStatus")}
          value={
            <Badge variant={modelStatusTone}>
              {modelLifecycleStatus
                ? t(`workflow.${modelLifecycleStatus}`, {
                    defaultValue: modelLifecycleStatus,
                  })
                : "-"}
            </Badge>
          }
        />
        <CardSummary
          label={t("workflow.deploymentStatus")}
          value={
            <Badge variant={attemptStatus.tone}>{t(attemptStatus.label)}</Badge>
          }
        />
      </div>

      <div className="flex flex-1 flex-col space-y-4">
        <TerminalViewer
          className="flex flex-1 flex-col min-h-80"
          bodyClassName="flex-1 min-h-64 h-full"
          logs={logs.logs}
          badge={
            <Badge variant={attemptStatus.tone}>{t(attemptStatus.label)}</Badge>
          }
          actionButtons={[
            {
              label: t("workflow.deploy"),
              icon: <Play className="h-4 w-4" />,
              type: "primary",
              loading:
                run.deploy.isPending ||
                Boolean(
                  run.selected &&
                  ["pending", "deploying"].includes(run.selected.status),
                ),
              disabled: !run.canDeploy || run.deploy.isPending,
              onClick: () =>
                run.deploy.mutate(undefined, {
                  onSuccess: (deployment) =>
                    navigate(
                      runDeploymentPath(projectId, buildId, deployment.id),
                      { replace: true },
                    ),
                }),
            },
          ]}
        />
        {run.busy && run.selected?.status !== "unconfirmed" && (
          <Callout
            variant="info"
            title={t("workflow.deploymentStatus")}
            description={t("workflow.deploymentBusyHint")}
          />
        )}
        {run.running && (
          <Callout
            variant="success"
            title={t("workflow.running")}
            description={t("workflow.deploySucceeded")}
          />
        )}
        {run.selected?.status === "unconfirmed" && (
          <Callout
            variant="warning"
            title={t("workflow.deployUnconfirmed")}
            description={t("workflow.unconfirmedHint")}
          />
        )}
        {run.selected && run.selected.status === "failed" && (
          <Callout
            variant="danger"
            title={t(attemptStatus.label)}
            description={
              run.selected.error_message || t("workflow.deployFailed")
            }
          />
        )}
        {error && (
          <Callout
            variant="danger"
            title={t("workflow.deployFailed")}
            description={getApiErrorMessage(error, t("workflow.deployFailed"))}
          />
        )}
        {logs.error && (
          <Callout
            variant="warning"
            title={t("workflow.logsUnavailable")}
            description={logs.error}
          />
        )}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Button
          type="button"
          variant="secondary"
          fullWidth
          onClick={() => navigate(buildDeploymentPath({ projectId, buildId }))}
        >
          {t("workflow.back")}
        </Button>
        <Button
          type="button"
          variant="primary"
          fullWidth
          disabled={!isDeploySuccess}
          onClick={() =>
            navigate(`/dashboard/projects/${projectId}/deployment`)
          }
        >
          {t("workflow.finish")}
        </Button>
      </div>
    </div>
  );
}
