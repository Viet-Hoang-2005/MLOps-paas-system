import { ArrowLeft, Check, Rocket } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { BuildSummaryItem } from "@/features/deploy/components/BuildSummaryItem";
import { useUploadModel } from "@/features/deploy/uploadModelContext";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { Button } from "@/shared/components/Button";
import { TerminalViewer } from "@/shared/components/TerminalViewer";

const DEPLOYMENT_TERMINAL_STATUSES = [
  "healthy",
  "unhealthy",
  "failed",
  "stopped",
] as const;

export default function DeployModelPage() {
  const { t } = useTranslation("deploy");
  const navigate = useNavigate();
  const {
    project,
    build,
    deployment,
    transitionState,
    deploy,
    goToStep,
    handleDeploymentCompleted,
  } = useUploadModel();
  const stream = useRuntimeLogStream({
    source: deployment?.id ? { kind: "deployment", id: deployment.id } : null,
    enabled: Boolean(deployment),
    terminalStatuses: DEPLOYMENT_TERMINAL_STATUSES,
  });

  useEffect(() => {
    if (
      stream.status &&
      DEPLOYMENT_TERMINAL_STATUSES.includes(
        stream.status as (typeof DEPLOYMENT_TERMINAL_STATUSES)[number],
      )
    ) {
      handleDeploymentCompleted(stream.status);
    }
  }, [handleDeploymentCompleted, stream.status]);

  if (!project || !build) return null;

  const running = Boolean(
    deployment && ["pending", "deploying"].includes(deployment.status),
  );
  const success = deployment?.status === "healthy";
  const failed = Boolean(
    deployment &&
    ["failed", "unhealthy", "stopped"].includes(deployment.status),
  );
  const deployStatus = !deployment
    ? t("uploadFlow.deploy.none")
    : success
      ? t("uploadFlow.deploy.success")
      : failed
        ? t("uploadFlow.deploy.error")
        : t("uploadFlow.deploy.deploying");

  return (
    <>
      <div className="rounded-surface border border-border bg-surface p-6 lg:p-8">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <BuildSummaryItem
            label={t("uploadFlow.deploy.model")}
            value={project.name}
          />
          <BuildSummaryItem
            label={t("uploadFlow.deploy.flavor")}
            value={build.flavor}
          />
          <BuildSummaryItem
            label={t("uploadFlow.deploy.version")}
            value={build.version_number ? `v${build.version_number}` : "-"}
          />
          <BuildSummaryItem
            label={t("uploadFlow.deploy.status")}
            value={deployStatus}
          />
        </div>

        <div className="mt-8">
          <TerminalViewer
            key={deployment?.id ?? "new-deployment"}
            title={t("uploadFlow.deploy.console")}
            logs={
              stream.error
                ? [...stream.logs, `Error: ${stream.error}`]
                : stream.logs
            }
            placeholder={t("uploadFlow.deploy.consolePlaceholder")}
          />
        </div>
      </div>

      <footer className="grid gap-3 pb-6 sm:grid-cols-2">
        <Button
          variant="secondary"
          size="md"
          icon={<ArrowLeft className="h-4 w-4" />}
          disabled={transitionState !== "idle" || running}
          onClick={() => void goToStep(2)}
        >
          {t("uploadFlow.actions.back")}
        </Button>
        <Button
          size="md"
          icon={
            success ? (
              <Check className="h-4 w-4" />
            ) : (
              <Rocket className="h-4 w-4" />
            )
          }
          disabled={running || transitionState !== "idle"}
          loading={running || transitionState === "starting-deployment"}
          onClick={() =>
            success ? navigate("/dashboard/home/models") : void deploy()
          }
        >
          {success
            ? t("uploadFlow.actions.finish")
            : failed
              ? t("uploadFlow.actions.retryDeploy")
              : running
                ? t("uploadFlow.actions.deploying")
                : t("uploadFlow.actions.deploy")}
        </Button>
      </footer>
    </>
  );
}
