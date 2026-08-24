import {
  Activity,
  Box,
  Check,
  CheckCircle2,
  Circle,
  Copy,
  ExternalLink,
  FileArchive,
  Globe,
  Loader2,
  PauseCircle,
  RefreshCw,
  Rocket,
  Settings,
  TerminalSquare,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button } from "@/shared/components/Button";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { BuildLogsPanel } from "./BuildLogsPanel";
import { toast } from "@/shared/components/toastStore";
import type { ModelProject } from "@/features/catalog/types";

// ── Helpers ────────────────────────────────────────────────────────────────

function isActiveModel(model: ModelProject) {
  return (
    model.build_status === "building" ||
    model.endpoint_status === "deploying" ||
    model.endpoint_status === "unhealthy"
  );
}

function LiveBadge() {
  const { t } = useTranslation("deploy");
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-primary-subtle px-2 py-0.5 text-style-caption font-bold uppercase text-color-primary ring-1 ring-inset ring-primary/20"
      title={t("deploymentCard.monitored")}
    >
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
      {t("deploymentCard.sync")}
    </span>
  );
}

// ── Component ──────────────────────────────────────────────────────────────

export interface ModelDeploymentCardProps {
  model: ModelProject;
  variant?: "full" | "compact";
  onCheckHealth?: (model: ModelProject) => void;
  isCheckingHealth?: boolean;
  onRedeploy?: (model: ModelProject) => void;
  isRedeploying?: boolean;
  onStop?: (model: ModelProject) => void;
  isStopping?: boolean;
  onCleanup?: (model: ModelProject) => void;
  isCleaningUp?: boolean;
  onOpenLogs?: (model: ModelProject) => void;
  onTestPrediction?: (model: ModelProject) => void;
  onOpenApiManagement?: (model: ModelProject) => void;
  onDeploy?: (model: ModelProject) => void;
  isDeploying?: boolean;
  onBuild?: (model: ModelProject) => void;
  isBuilding?: boolean;
}

export function ModelDeploymentCard({
  model,
  variant = "full",
  onCheckHealth,
  isCheckingHealth,
  onRedeploy,
  isRedeploying,
  onStop,
  isStopping,
  onCleanup,
  isCleaningUp,
  onOpenLogs,
  onTestPrediction,
  onOpenApiManagement,
  onDeploy,
  isDeploying,
  onBuild,
  isBuilding,
}: ModelDeploymentCardProps) {
  const { t } = useTranslation("deploy");
  const navigate = useNavigate();
  const [copied, setCopied] = useState(false);
  const [showStopModal, setShowStopModal] = useState(false);
  const [showCleanupModal, setShowCleanupModal] = useState(false);

  const endpointStatus = model.endpoint_status || "not_deployed";
  const readyToDeploy = model.build_status === "ready";
  const isHealthy = endpointStatus === "healthy";
  const isDeployingState = endpointStatus === "deploying";
  const isBuildingState = model.build_status === "building";
  const isStopped = endpointStatus === "stopped";

  // Actions
  const canRedeploy = readyToDeploy && !isDeployingState;
  const canStop =
    endpointStatus !== "not_deployed" && !isStopped && !isDeployingState;

  const copyEndpoint = async () => {
    if (!model.endpoint_url) return;
    await navigator.clipboard.writeText(model.endpoint_url);
    setCopied(true);
    toast.success(t("deploymentCard.endpointCopied"));
    setTimeout(() => setCopied(false), 2000);
  };

  // Top Accent Logic
  let accentClass = "border-t-gray-200";
  let badgeClass = "bg-muted text-color-foreground border-border";
  let statusText = t("deploymentCard.statuses.notDeployed");

  if (isHealthy) {
    accentClass = "border-t-emerald-500";
    badgeClass = "bg-success-subtle text-color-success border-success/20";
    statusText = t("deploymentCard.statuses.healthy");
  } else if (
    endpointStatus === "unhealthy" ||
    endpointStatus === "deploy_failed" ||
    model.build_status === "error"
  ) {
    accentClass = "border-t-red-500";
    badgeClass = "bg-danger-subtle text-color-danger border-danger/20";
    statusText =
      model.build_status === "error"
        ? t("deploymentCard.statuses.buildFailed")
        : t("deploymentCard.statuses.unhealthy");
  } else if (isDeployingState || isBuildingState) {
    accentClass = "border-t-blue-500";
    badgeClass =
      "bg-primary-subtle text-color-primary border-primary/20 animate-pulse";
    statusText = isBuildingState
      ? t("deploymentCard.statuses.building")
      : t("deploymentCard.statuses.deploying");
  } else if (isStopped) {
    accentClass = "border-t-gray-400";
    badgeClass = "bg-muted text-color-muted-foreground border-border";
    statusText = t("deploymentCard.statuses.stopped");
  } else if (readyToDeploy) {
    accentClass = "border-t-blue-300";
    badgeClass = "bg-primary-subtle text-color-primary border-primary/20";
    statusText = t("deploymentCard.statuses.buildReady");
  }

  // Lifecycle Tracker State
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
    <article
      className={`relative flex flex-col rounded-surface border bg-surface shadow-sm transition-all hover:shadow-md border-t-4 border-x-gray-200 border-b-gray-200 ${accentClass} ${
        variant === "compact" ? "p-5" : "p-6 lg:p-8"
      }`}
    >
      {/* ── Header Area ── */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div className="flex items-start gap-4">
          <div className="hidden sm:flex h-12 w-12 shrink-0 items-center justify-center rounded-surface bg-muted border border-border text-color-muted-foreground shadow-inner">
            <Box className="h-6 w-6" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                className="text-style-heading font-bold text-color-foreground hover:text-color-primary transition-colors focus:outline-none"
                onClick={() => {
                  if (onOpenApiManagement) onOpenApiManagement(model);
                  else navigate(`/dashboard/management/model/${model.id}`);
                }}
              >
                {model.name}
              </button>
              <span className="rounded-full bg-muted px-2 py-0.5 text-style-caption-strong text-color-muted-foreground border border-border">
                {model.version || "v1"}
              </span>
              <span
                className={`rounded-full border px-2.5 py-0.5 text-style-caption font-bold uppercase ${badgeClass}`}
              >
                {statusText}
              </span>
            </div>
            <p className="mt-1 text-style-caption text-color-muted-foreground font-medium">
              {model.source_type === "training_job"
                ? t("deploymentCard.registeredFromTraining", {
                    jobId: model.source_training_job ?? "-",
                  })
                : t("deploymentCard.manualUpload")}
            </p>
          </div>
        </div>

        {isActiveModel(model) && (
          <div className="flex shrink-0">
            <LiveBadge />
          </div>
        )}
      </div>

      {variant === "full" && model.description && (
        <p className="mt-4 max-w-3xl text-style-body text-color-muted-foreground">
          {model.description}
        </p>
      )}

      {/* ── Lifecycle Tracker ── */}
      <div className="mt-8 flex items-center w-full max-w-2xl overflow-x-auto pb-2 scrollbar-none">
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

      {/* ── Metadata & Endpoint ── */}
      <div className="mt-8 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Endpoint URL Block */}
        <div className="lg:col-span-7 flex flex-col justify-end">
          <label className="mb-2 block text-style-caption font-bold uppercase text-color-muted-foreground">
            {t("deploymentCard.endpointUrl")}
          </label>
          {model.endpoint_url ? (
            <div className="group flex items-center overflow-hidden rounded-surface border border-border bg-muted shadow-sm transition-colors hover:border-border">
              <div className="flex items-center justify-center bg-muted px-3 py-2 border-r border-border text-color-muted-foreground">
                <Globe className="h-4 w-4" />
              </div>
              <code
                className="flex-1 truncate bg-transparent px-3 py-2 font-mono text-style-code-sm text-color-foreground"
                title={model.endpoint_url}
              >
                {model.endpoint_url}
              </code>
              <button
                onClick={copyEndpoint}
                className="flex items-center justify-center px-3 py-2 text-color-muted-foreground hover:bg-surface hover:text-color-foreground border-l border-transparent hover:border-border transition-all focus:outline-none"
                title={t("deploymentCard.copyUrl")}
              >
                {copied ? (
                  <Check className="h-4 w-4 text-color-success" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </button>
            </div>
          ) : (
            <div className="flex h-9 items-center rounded-surface border border-border border-dashed bg-muted/50 px-3 py-2">
              <p className="font-mono text-style-code-sm text-color-muted-foreground">
                {t("deploymentCard.endpointMissing")}
              </p>
            </div>
          )}
        </div>

        {/* Diagnostics Grid */}
        <div className="lg:col-span-5 grid grid-cols-2 gap-4">
          <div className="flex flex-col justify-end">
            <span className="mb-1 text-style-caption font-bold uppercase text-color-muted-foreground">
              {t("deploymentCard.container")}
            </span>
            <span
              className="truncate font-mono text-style-code-sm text-color-foreground bg-muted rounded-compact px-2 py-1 border border-border w-fit max-w-full"
              title={model.endpoint_container_name || ""}
            >
              {model.endpoint_container_name || t("statuses.notAvailable", { ns: "common" })}
            </span>
          </div>
          <div className="flex flex-col justify-end">
            <span className="mb-1 text-style-caption font-bold uppercase text-color-muted-foreground">
              {t("deploymentCard.lastChecked")}
            </span>
            <span className="truncate text-style-caption text-color-foreground bg-muted rounded-compact px-2 py-1 border border-border w-fit max-w-full">
              {model.endpoint_last_checked_at
                ? new Date(model.endpoint_last_checked_at).toLocaleString()
                : t("statuses.notAvailable", { ns: "common" })}
            </span>
          </div>
        </div>
      </div>

      {/* Errors / Logs */}
      {(model.build_error || model.endpoint_error) && (
        <div className="mt-6 rounded-surface border border-danger/20 bg-danger-subtle p-4">
          <p className="text-style-body-strong text-color-danger flex items-center gap-2">
            <XCircle className="h-4 w-4" />
            {t("deploymentCard.deploymentError")}
          </p>
          <p className="mt-1 text-style-body text-color-danger font-medium">
            {model.build_error || model.endpoint_error}
          </p>
        </div>
      )}

      {isBuildingState && (
        <div className="mt-6">
          <BuildLogsPanel modelId={model.id} />
        </div>
      )}

      {/* ── Action Toolbar ── */}
      <div className="mt-8 flex flex-col sm:flex-row flex-wrap items-center justify-between gap-4 border-t border-border pt-5">
        {/* Primary / Operational Group */}
        <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto flex-1">
          {/* Primary Action */}
          {!readyToDeploy && onBuild ? (
            <Button
              size="md"
              variant="primary"
              icon={<FileArchive className="h-4 w-4" />}
              loading={isBuilding}
              disabled={isBuildingState}
              onClick={() => onBuild(model)}
            >
              {t("actions.buildPackage")}
            </Button>
          ) : endpointStatus === "not_deployed" && onDeploy ? (
            <Button
              size="md"
              variant="primary"
              icon={<Rocket className="h-4 w-4" />}
              loading={isDeploying}
              disabled={isDeployingState}
              onClick={() => onDeploy(model)}
            >
              {t("actions.deployEndpoint")}
            </Button>
          ) : onRedeploy && readyToDeploy ? (
            <Button
              size="md"
              variant={isHealthy ? "secondary" : "primary"}
              icon={<RefreshCw className="h-4 w-4" />}
              loading={isRedeploying}
              disabled={!canRedeploy}
              onClick={() => onRedeploy(model)}
            >
              {t("actions.redeploy")}
            </Button>
          ) : null}

          {/* Operational Actions */}
          {model.endpoint_url && onCheckHealth && (
            <Button
              size="md"
              variant="secondary"
              icon={<Activity className="h-4 w-4" />}
              loading={isCheckingHealth}
              onClick={() => onCheckHealth(model)}
            >
              {t("actions.checkHealth")}
            </Button>
          )}

          {onOpenLogs && model.endpoint_container_name && (
            <Button
              size="md"
              variant="secondary"
              icon={<TerminalSquare className="h-4 w-4" />}
              onClick={() => onOpenLogs(model)}
            >
              {t("actions.logs")}
            </Button>
          )}

          {onTestPrediction && (
            <Button
              size="md"
              variant="secondary"
              icon={<ExternalLink className="h-4 w-4" />}
              onClick={() => onTestPrediction(model)}
              disabled={!isHealthy}
            >
              {t("actions.testPrediction")}
            </Button>
          )}

          {onOpenApiManagement && variant === "compact" && (
            <Button
              size="md"
              variant="secondary"
              icon={<Settings className="h-4 w-4" />}
              onClick={() => onOpenApiManagement(model)}
            >
              {t("actions.manage")}
            </Button>
          )}
        </div>

        {/* Danger / Maintenance Group */}
        {(onStop || onCleanup) && (
          <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto sm:border-l sm:border-border sm:pl-4">
            {onStop && endpointStatus !== "not_deployed" && (
              <Button
                size="md"
                variant="danger-outline"
                icon={<PauseCircle className="h-4 w-4" />}
                loading={isStopping}
                disabled={!canStop}
                onClick={() => setShowStopModal(true)}
              >
                {t("actions.stopEndpoint")}
              </Button>
            )}

            {onCleanup && (
              <Button
                size="md"
                variant="ghost"
                icon={<FileArchive className="h-4 w-4" />}
                loading={isCleaningUp}
                onClick={() => setShowCleanupModal(true)}
                className="border border-warning-border text-color-warning hover:border-warning hover:bg-warning-subtle active:bg-warning active:text-color-warning-foreground"
              >
                {t("actions.cleanup")}
              </Button>
            )}
          </div>
        )}
      </div>

      {/* ── Confirmation Modals ── */}
      {onStop && (
        <ConfirmModal
          open={showStopModal}
          title={t("deploymentCard.stopTitle")}
          description={t("deploymentCard.stopDescription")}
          confirmText={t("deploymentCard.stopConfirm")}
          cancelText={t("actions.cancel", { ns: "common" })}
          tone="danger"
          loading={isStopping}
          onConfirm={() => {
            onStop(model);
            setShowStopModal(false);
          }}
          onCancel={() => setShowStopModal(false)}
        />
      )}

      {onCleanup && (
        <ConfirmModal
          open={showCleanupModal}
          title={t("deploymentCard.cleanupTitle")}
          description={t("deploymentCard.cleanupDescription")}
          confirmText={t("deploymentCard.cleanupConfirm")}
          cancelText={t("actions.cancel", { ns: "common" })}
          tone="default"
          loading={isCleaningUp}
          onConfirm={() => {
            onCleanup(model);
            setShowCleanupModal(false);
          }}
          onCancel={() => setShowCleanupModal(false)}
        />
      )}
    </article>
  );
}

// ── Lifecycle Tracker Components ──────────────────────────────────────────

function TrackerStep({ label, state }: { label: string; state: string }) {
  const isCompleted = state === "completed";
  const isActive = state === "active";
  const isFailed = state === "failed";
  const isNeutral = state === "neutral";

  let icon = <Circle className="h-2.5 w-2.5 fill-current" />;
  if (isCompleted) icon = <CheckCircle2 className="h-4 w-4" />;
  else if (isFailed) icon = <XCircle className="h-4 w-4" />;
  else if (isActive) icon = <Loader2 className="h-4 w-4 animate-spin" />;
  else if (isNeutral) icon = <PauseCircle className="h-4 w-4" />;

  let colorClass = "text-color-muted-foreground";
  if (isCompleted) colorClass = "text-color-success";
  else if (isActive) colorClass = "text-color-info";
  else if (isFailed) colorClass = "text-color-danger";
  else if (isNeutral) colorClass = "text-color-muted-foreground";

  let textClass = "text-color-muted-foreground font-medium";
  if (isCompleted) textClass = "text-color-foreground font-bold";
  else if (isActive) textClass = "text-color-info font-bold";
  else if (isFailed) textClass = "text-color-danger font-bold";
  else if (isNeutral) textClass = "text-color-muted-foreground font-bold";

  return (
    <div className="flex flex-col items-center gap-2 w-20 shrink-0">
      <div
        className={`flex h-6 w-6 items-center justify-center rounded-full bg-surface ring-4 ring-background ${colorClass}`}
      >
        {icon}
      </div>
      <span
        className={`text-style-caption uppercase text-center ${textClass}`}
      >
        {label}
      </span>
    </div>
  );
}

function TrackerLine({ state }: { state: "completed" | "pending" }) {
  return (
    <div className="flex-1 shrink-0 px-2 -mt-6">
      <div
        className={`h-0.5 w-full rounded-full ${state === "completed" ? "bg-success" : "bg-muted"}`}
      />
    </div>
  );
}
