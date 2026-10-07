import type { ModelProject } from "@/features/projects/types";
import { currentApiHealth } from "@/features/overview/runtimeHealth";
import { formatDateTime } from "@/shared/i18n/formatters";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import {
  ProgressLine,
  type ProgressLineStep,
} from "@/shared/components/ProgressLine";
import { StepTitle } from "@/shared/components/StepTitle";
import { toast } from "@/shared/types/toastStore";
import { Activity, Bot, Check, Copy, Package, GitBranch } from "lucide-react";
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
  const [copied, setCopied] = useState(false);
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

  const endpointUrl = model.endpoint_url || model.active_endpoint?.url || "";

  const handleCopy = () => {
    if (endpointUrl) {
      void navigator.clipboard.writeText(endpointUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success(t("workflow.endpointCopied"));
    }
  };

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
        <StepTitle
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

      <div className="flex flex-col gap-3 rounded-surface border border-border bg-muted/30 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span className="shrink-0 text-style-body-strong uppercase text-color-muted-foreground">
            {t("workflow.apiUrl")}
          </span>
          <code className="min-w-0 flex-1 break-all select-all font-mono text-style-body font-medium text-color-foreground">
            {endpointUrl}
          </code>
        </div>
        <Button
          size="sm"
          variant="secondary"
          icon={
            copied ? (
              <Check className="h-4 w-4" />
            ) : (
              <Copy className="h-4 w-4" />
            )
          }
          onClick={handleCopy}
          className="shrink-0"
        >
          {copied ? t("workflow.copied") : t("workflow.copyEndpoint")}
        </Button>
      </div>
    </section>
  );
}
