import type { ModelProject } from "@/features/projects/types";
import { currentApiHealth } from "@/features/overview/runtimeHealth";
import { formatDateTime } from "@/shared/i18n/formatters";
import { Badge } from "@/shared/components/Badge";
import { TerminalViewer } from "@/shared/components/TerminalViewer";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { Callout } from "@/shared/components/Callout";
import { Loading } from "@/shared/components/Loading";
import {
  ProgressLine,
  type ProgressLineStep,
} from "@/shared/components/ProgressLine";
import { Title } from "@/shared/components/Title";
import { Activity, Bot, Package, GitBranch } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

export function ModelStatusLine({
  model,
  healthUnavailable = false,
}: {
  model: ModelProject;
  healthUnavailable?: boolean;
}) {
  const { t, i18n } = useTranslation("overview");
  const monitoring = model.active_endpoint?.deployment_status === "succeeded";
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!monitoring) return;
    const timer = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(timer);
  }, [monitoring]);
  const healthStatus = currentApiHealth(
    model.active_endpoint,
    healthUnavailable,
    now,
  );

  const modelStatusSteps = useMemo<ProgressLineStep[]>(() => {
    const registrationStatus =
      model.active_endpoint?.registration_status ?? "unregistered";
    return [
      {
        id: "artifact",
        label: t("workflow.stepArtifact"),
        state: "completed",
        icon: Bot,
        helper: t("workflow.stepArtifactHelper"),
      },
      {
        id: "build_image",
        label: t("workflow.stepBuildImage"),
        state: "completed",
        icon: Package,
        helper: t("workflow.stepBuildImageHelper"),
      },
      {
        id: "register_model",
        label: t("workflow.stepRegisterModel"),
        state:
          registrationStatus === "failed"
            ? "failed"
            : registrationStatus !== "registered"
              ? "active"
              : "completed",
        icon: GitBranch,
        helper:
          registrationStatus === "registered"
            ? t("workflow.stepRegisterModelHelper")
            : t(`workflow.${registrationStatus}`),
      },
      {
        id: "api_health",
        label: t("workflow.stepApiHealth"),
        state:
          healthStatus === "healthy"
            ? "completed"
            : healthStatus === "unhealthy"
              ? "failed"
              : "active",
        icon: Activity,
        helper: monitoring
          ? `${t("workflow.health")}: ${t(`workflow.${healthStatus}`)}`
          : t("workflow.healthNotChecked"),
      },
    ];
  }, [model.active_endpoint?.registration_status, healthStatus, monitoring, t]);

  const healthSubtitle = `${
    healthUnavailable
      ? t("workflow.healthUnavailable")
      : monitoring
        ? t("workflow.healthMonitoringHint")
        : t("workflow.healthNotChecked")
  }${
    model.active_endpoint?.last_checked_at
      ? ` · ${t("workflow.healthLastChecked", { time: formatDateTime(model.active_endpoint.last_checked_at, i18n.language) })}`
      : ""
  }`;

  return (
    <section className="space-y-6 rounded-surface border border-border bg-surface p-6">
      <div className="flex items-start justify-between gap-4">
        <Title
          title={t("workflow.modelStatus")}
          subtitle={healthSubtitle}
          className="mb-0"
        />
        <Badge
          variant={
            healthStatus === "healthy"
              ? "success"
              : healthStatus === "unhealthy"
                ? "danger"
                : "neutral"
          }
        >
          {t("workflow.health")}:{" "}
          {monitoring
            ? t(`workflow.${healthStatus}`)
            : t("workflow.healthNotChecked")}
        </Badge>
      </div>

      <div className="overflow-x-auto pb-2">
        <ProgressLine steps={modelStatusSteps} />
      </div>

      <RuntimeLogs deploymentId={model.active_endpoint?.deployment_id ?? ""} />
    </section>
  );
}

function RuntimeLogs({ deploymentId }: { deploymentId: string }) {
  const { t } = useTranslation("overview");
  const logs = useRuntimeLogStream({
    source: deploymentId ? { kind: "deployment_runtime", id: deploymentId } : null,
  });
  return (
    <div className="space-y-2">
      <TerminalViewer
        title={t("workflow.runtimeLogs")}
        logs={logs.logs}
        placeholder={deploymentId && !logs.status && !logs.error ? <Loading size="sm" /> : t("workflow.noRuntimeLogs")}
      />
      {logs.error && <Callout variant="warning" title={t("workflow.runtimeLogsUnavailable")} description={logs.error} />}
    </div>
  );
}
