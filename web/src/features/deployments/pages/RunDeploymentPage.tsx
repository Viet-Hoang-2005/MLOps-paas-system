import { RouteFallback } from "@/app/router/RouteFallback";
import { deploymentStatuses } from "@/features/deployments/buildHistoryStatus";
import { isDeployableBuild } from "@/features/deployments/deploymentEligibility";
import { useRunDeployment } from "@/features/deployments/hooks/useRunDeployment";
import {
  buildDeploymentPath,
  runDeploymentPath,
} from "@/features/deployments/navigation";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { PageHeader } from "@/shared/components/PageHeader";
import { Select } from "@/shared/components/Select";
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
    terminalStatuses: [
      "healthy",
      "failed",
      "unhealthy",
      "stopped",
      "unconfirmed",
    ],
  });
  const attemptStatus =
    deploymentStatuses[run.selected?.status ?? "not_deployed"];
  const options = (run.history.data ?? [])
    .filter((build) => isDeployableBuild(build, projectId))
    .map((build) => ({
      value: build.id,
      label: `v${build.version_number} · ${build.id}`,
    }));
  const error = run.error || run.deploy.error;
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
      <section className="flex flex-1 flex-col space-y-6 rounded-surface border border-border bg-surface p-6">
        <h2 className="text-style-heading">{run.project.data?.name}</h2>
        <Select
          value={buildId}
          options={options}
          placeholder={t("workflow.selectVersion")}
          disabled={run.loading || run.deploy.isPending || Boolean(run.busy)}
          onChange={(id) => navigate(runDeploymentPath(projectId, id))}
        />
        <dl className="space-y-2 break-all">
          <dt className="text-style-caption-strong">{t("workflow.buildId")}</dt>
          <dd className="text-style-code-sm">{buildId}</dd>
          <dt className="text-style-caption-strong">
            {t("workflow.readyImageUri")}
          </dt>
          <dd className="text-style-code-sm">{run.build.data?.image_uri}</dd>
        </dl>
        <TerminalViewer
          className="flex flex-1 flex-col min-h-72"
          bodyClassName="flex-1 min-h-72 h-full"
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
            description={t("workflow.deployHealthy")}
          />
        )}
        {run.selected?.status === "unconfirmed" && (
          <Callout
            variant="warning"
            title={t("workflow.deployUnconfirmed")}
            description={t("workflow.unconfirmedHint")}
          />
        )}
        {run.selected &&
          ["failed", "unhealthy"].includes(run.selected.status) && (
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
      </section>
      <div className="flex flex-wrap gap-3">
        <Button
          variant="secondary"
          onClick={() =>
            navigate(`/dashboard/projects/${projectId}/deployment`)
          }
        >
          {t("workflow.deployment")}
        </Button>
        <Button
          variant="primary"
          disabled={!run.running}
          onClick={() => navigate(`/dashboard/projects/${projectId}/overview`)}
        >
          {t("workflow.openOverview")}
        </Button>
      </div>
    </div>
  );
}
