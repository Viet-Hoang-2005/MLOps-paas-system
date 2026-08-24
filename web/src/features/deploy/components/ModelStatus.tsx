import type { ModelProject } from "@/features/catalog/types";
import {
  Activity,
  CheckCircle2,
  Circle,
  Info,
  Loader2,
  PauseCircle,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";

function TrackerStep({ label, state }: { label: string; state: string }) {
  const isCompleted = state === "completed";
  const isActive = state === "active";
  const isFailed = state === "failed";
  const isNeutral = state === "neutral";

  let icon = <Circle className="h-2.5 w-2.5 fill-current" />;
  if (isCompleted) icon = <CheckCircle2 className="h-6 w-6" />;
  else if (isFailed) icon = <XCircle className="h-6 w-6" />;
  else if (isActive) icon = <Loader2 className="h-6 w-6 animate-spin" />;
  else if (isNeutral) icon = <PauseCircle className="h-6 w-6" />;

  let colorClass = "text-color-muted-foreground";
  if (isCompleted) colorClass = "text-color-success";
  else if (isActive) colorClass = "text-color-primary";
  else if (isFailed) colorClass = "text-color-danger";
  else if (isNeutral) colorClass = "text-color-muted-foreground";

  let textClass = "text-color-muted-foreground font-medium";
  if (isCompleted) textClass = "text-color-foreground font-bold";
  else if (isActive) textClass = "text-color-primary font-bold";
  else if (isFailed) textClass = "text-color-danger font-bold";
  else if (isNeutral) textClass = "text-color-muted-foreground font-bold";

  return (
    <div className="flex w-24 shrink-0 flex-col items-center gap-2">
      <div
        className={`flex h-6 w-6 items-center justify-center rounded-full bg-surface ring-4 ring-background ${colorClass}`}
      >
        {icon}
      </div>
      <span
        className={`text-center text-style-caption uppercase ${textClass}`}
      >
        {label}
      </span>
    </div>
  );
}

function TrackerLine({ state }: { state: "completed" | "pending" }) {
  return (
    <div className="-mt-6 flex-1 shrink-0 px-2">
      <div
        className={`h-0.5 w-full rounded-full ${state === "completed" ? "bg-success" : "bg-muted"}`}
      />
    </div>
  );
}

export function ModelStatus({ model }: { model: ModelProject }) {
  const { t } = useTranslation("deploy");
  const endpointStatus = model.endpoint_status || "not_deployed";
  const isBuildingState = model.build_status === "building";
  const isDeployingState = endpointStatus === "deploying";
  const isHealthy = endpointStatus === "healthy";
  const isStopped = endpointStatus === "stopped";

  const stage0 = "completed" as const;
  let stage1: "pending" | "active" | "completed" | "failed" = "pending";
  let stage2: "pending" | "active" | "completed" | "failed" | "neutral" =
    "pending";
  let stage3: "pending" | "active" | "completed" | "failed" = "pending";

  if (isBuildingState) stage1 = "active";
  else if (model.build_status === "error") stage1 = "failed";
  else if (model.build_status === "ready") stage1 = "completed";

  if (stage1 === "completed") {
    if (isDeployingState) stage2 = "active";
    else if (endpointStatus === "deploy_failed") stage2 = "failed";
    else if (isStopped) stage2 = "neutral";
    else if (endpointStatus !== "not_deployed") stage2 = "completed";
  }

  if (stage2 === "completed") {
    if (isHealthy) stage3 = "completed";
    else if (endpointStatus === "unhealthy") stage3 = "failed";
    else stage3 = "active"; // checking
  }

  return (
    <div className="flex flex-col gap-6">
      {/* ── Lifecycle Tracker ── */}
      <div className="flex w-full items-center overflow-x-auto pb-2 scrollbar-none max-w-2xl mx-auto mt-4 mb-4">
        <TrackerStep label={t("lifecycle.registered")} state={stage0} />
        <TrackerLine
          state={
            stage1 === "completed" || stage1 === "active"
              ? "completed"
              : "pending"
          }
        />
        <TrackerStep label={t("lifecycle.buildReady")} state={stage1} />
        <TrackerLine
          state={
            stage2 === "completed" ||
            stage2 === "active" ||
            stage2 === "neutral"
              ? "completed"
              : "pending"
          }
        />
        <TrackerStep label={t("lifecycle.deployed")} state={stage2} />
        <TrackerLine
          state={
            stage3 === "completed" || stage3 === "active" || stage3 === "failed"
              ? "completed"
              : "pending"
          }
        />
        <TrackerStep label={t("lifecycle.healthy")} state={stage3} />
      </div>

      {/* ── Deprecation Notice for Realtime Pod Logs ── */}
      <div className="rounded-surface border border-warning/20 bg-warning-subtle p-6">
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-surface bg-warning/10 text-color-warning">
            <Activity className="h-6 w-6" />
          </div>
          <div className="flex-1 space-y-2">
            <h4 className="text-style-heading text-color-foreground flex items-center gap-2">
              <span>{t("lifecycle.logsDeprecated")}</span>
              <span className="inline-flex items-center rounded-full bg-warning/10 px-2.5 py-0.5 text-style-caption font-semibold text-color-warning">
                {t("lifecycle.prometheus")}
              </span>
            </h4>
            <p className="text-style-body text-color-muted-foreground">
              {t("lifecycle.logsDescription")}
            </p>
            <div className="pt-2 flex items-center gap-2 text-style-caption-strong text-color-warning">
              <Info className="h-4 w-4" />
              <span>{t("lifecycle.logsHint")}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
