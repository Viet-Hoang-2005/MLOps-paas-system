import { useState } from "react";
import type {
  RegistryFamily,
  RegistryModelInsightItem,
  RegistryVersion,
} from "@/features/registry/types";
import {
  Copy,
  Terminal,
  ExternalLink,
  ArrowUpCircle,
  RotateCcw,
  GitCompare,
  Check,
  FileText,
  Gauge,
  SlidersHorizontal,
  ShieldCheck,
  Rocket,
  HeartPulse,
  Play,
  BarChart3,
} from "lucide-react";
import { formatVersion } from "@/shared/lib/formatters";
import { Button } from "@/shared/components/Button";
import { toast } from "@/shared/components/toastStore";
import {
  checkRegistryVersionHealth,
  deployRegistryVersion,
  smokeTestRegistryVersion,
} from "@/features/registry/api/registryApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { useTranslation } from "react-i18next";

import { ModelMetricsPanel } from "./ModelMetricsPanel";
import { ModelHistoryTimeline } from "./ModelHistoryTimeline";
import { DriftSummaryCard } from "./DriftSummaryCard";
import { PromoteVersionModal } from "./PromoteVersionModal";
import { RollbackVersionModal } from "./RollbackVersionModal";
import { VersionComparisonModal } from "./VersionComparisonModal";

interface Props {
  family: RegistryFamily;
  version: RegistryVersion;
  allVersions: RegistryVersion[];
  onActionSuccess: () => void;
}

type NormalizedInsightItem = RegistryModelInsightItem & {
  value: number;
  abs_value: number;
};

const classNames = (...classes: (string | undefined | null | false)[]) =>
  classes.filter(Boolean).join(" ");

function formatValue(value: unknown): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toString() : value.toFixed(4);
  }
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "-";
  return JSON.stringify(value, null, 2);
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function shortValue(value: unknown, maxLength = 96): string {
  const formatted = formatValue(value).replace(/\s+/g, " ").trim();
  return formatted.length > maxLength
    ? `${formatted.slice(0, maxLength - 1)}…`
    : formatted;
}

function formatBytes(size?: number): string {
  if (!size && size !== 0) return "-";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatInsightValue(value?: number): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  const abs = Math.abs(value);
  if (abs !== 0 && abs < 0.0001) return value.toExponential(3);
  if (abs >= 1000)
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function numericInsightValue(value: unknown): number | null {
  if (typeof value === "number" && !Number.isNaN(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
}

function numericMetricValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function deployabilityBadge(status?: string) {
  switch (status) {
    case "deployable":
      return "bg-success-subtle text-color-success border-success/20";
    case "track_only":
      return "bg-warning-subtle text-color-warning border-warning/20";
    case "invalid":
      return "bg-danger-subtle text-color-danger border-danger/20";
    default:
      return "bg-muted text-color-foreground border-border";
  }
}

function trackingBadge(status?: string) {
  switch (status) {
    case "completed":
      return "bg-success-subtle text-color-success border-success/20";
    case "skipped":
      return "bg-primary-subtle text-color-primary border-primary/20";
    case "failed":
      return "bg-warning-subtle text-color-warning border-warning/20";
    case "ingesting":
      return "bg-primary-subtle text-color-primary border-primary/20";
    default:
      return "bg-muted text-color-muted-foreground border-border";
  }
}

function trackingLabelKey(status?: string) {
  switch (status) {
    case "completed":
      return "versionDetail.tracking.logged" as const;
    case "skipped":
      return "versionDetail.tracking.nativeIngested" as const;
    case "failed":
      return "versionDetail.tracking.loggingFailed" as const;
    case "ingesting":
      return "versionDetail.tracking.ingesting" as const;
    default:
      return "versionDetail.tracking.notSynced" as const;
  }
}

function trackingDescriptionKey(status?: string) {
  switch (status) {
    case "completed":
      return "versionDetail.tracking.loggedDescription" as const;
    case "skipped":
      return "versionDetail.tracking.nativeDescription" as const;
    case "failed":
      return "versionDetail.tracking.failedDescription" as const;
    case "ingesting":
      return "versionDetail.tracking.ingestingDescription" as const;
    default:
      return "versionDetail.tracking.notSyncedDescription" as const;
  }
}

function endpointFriendlyHint(reasonCode: string | undefined, fallback: string): string {
  if (!reasonCode) return "";
  if (
    [
      "ENDPOINT_CONTAINER_NOT_FOUND",
      "ENDPOINT_NOT_REACHABLE",
      "ENDPOINT_TIMEOUT",
      "LOCAL_RUNTIME_NOT_STARTED",
    ].includes(reasonCode)
  ) {
    return fallback;
  }
  return "";
}

function endpointActionMessage(result: {
  message?: string;
  reason_code?: string;
  endpoint_error?: string;
  error?: string;
  success?: boolean;
}, messages: {
  notReachable: string;
  failed: string;
  completed: string;
}): string {
  return (
    result.message ||
    endpointFriendlyHint(result.reason_code, messages.notReachable) ||
    result.endpoint_error ||
    result.error ||
    (result.success === false
      ? messages.failed
      : messages.completed)
  );
}

function withoutTechnicalDetail(value: unknown): unknown {
  if (!value || typeof value !== "object" || Array.isArray(value)) return value;
  const rest = { ...(value as Record<string, unknown>) };
  delete rest.technical_detail;
  return rest;
}

// ---------------------------------------------------------------------------
// DriftSummaryCard — lightweight drift indicator for Model Evolution detail
// ---------------------------------------------------------------------------
export function ModelVersionDetail({
  family,
  version,
  allVersions,
  onActionSuccess,
}: Props) {
  const { t } = useTranslation("registry");
  const [activeTab, setActiveTab] = useState<
    "details" | "insights" | "metrics" | "history"
  >("details");
  const [isPromoteModalOpen, setIsPromoteModalOpen] = useState(false);
  const [isRollbackModalOpen, setIsRollbackModalOpen] = useState(false);
  const [isCompareModalOpen, setIsCompareModalOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState<
    "deploy" | "health" | "smoke" | null
  >(null);
  const [smokePayload, setSmokePayload] = useState('{\n  "features": {}\n}');
  const [actionResult, setActionResult] = useState<string>("");
  const [smokeResult, setSmokeResult] = useState<unknown>(null);
  const [technicalDetail, setTechnicalDetail] = useState<string>("");

  const isProd = version.stage === "production";

  const [copied, setCopied] = useState(false);
  const metricsSummary =
    version.metrics_summary || version.metricsSummary || {};
  const paramsSummary = version.params_summary || version.paramsSummary || {};
  const metricEntries = Object.entries(metricsSummary);
  const scalarMetricEntries = metricEntries.filter(
    ([, value]) => !isPlainRecord(value) && !Array.isArray(value),
  );
  const objectMetricEntries = metricEntries.filter(
    ([, value]) => isPlainRecord(value) || Array.isArray(value),
  );
  const numericMetricEntries = metricEntries
    .map(([name, value]) => ({
      name,
      value,
      numericValue: numericMetricValue(value),
    }))
    .filter(
      (
        entry,
      ): entry is { name: string; value: unknown; numericValue: number } =>
        entry.numericValue !== null,
    );
  const maxMetricAbs = Math.max(
    ...numericMetricEntries.map((entry) => Math.abs(entry.numericValue)),
    0,
  );
  const paramEntries = Object.entries(paramsSummary);
  const artifactEntries =
    version.artifact_manifest || version.artifactManifest || [];
  const modelInsights =
    version.model_insights_summary || version.modelInsightsSummary || {};
  const insightItems = (modelInsights.items || [])
    .reduce<NormalizedInsightItem[]>((items, item) => {
      const value = numericInsightValue(item?.value);
      if (!item || typeof item.name !== "string" || value === null)
        return items;
      const absValue = numericInsightValue(item.abs_value) ?? Math.abs(value);
      items.push({
        ...item,
        value,
        abs_value: absValue,
      });
      return items;
    }, [])
    .sort(
      (left, right) =>
        (right.abs_value ?? Math.abs(right.value)) -
        (left.abs_value ?? Math.abs(left.value)),
    );
  const topInsightItems = insightItems.slice(0, 20);
  const maxInsightAbs = Math.max(
    ...topInsightItems.map((item) => item.abs_value ?? Math.abs(item.value)),
    0,
  );
  const insightKind = modelInsights.kind || "unknown";
  const topInsightItem = insightItems[0];
  const insightItemCount =
    version.model_insights_item_count ||
    version.modelInsightsItemCount ||
    insightItems.length;
  const routingAliases =
    version.routing_aliases || version.routingAliases || [];
  const canPromote = version.can_promote ?? version.canPromote ?? false;

  const copyEndpoint = async () => {
    if (!version.endpoint_url) return;
    await navigator.clipboard.writeText(version.endpoint_url);
    toast.success(t("versionDetail.endpointCopied"));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const copyText = async (text: string, message: string) => {
    await navigator.clipboard.writeText(text);
    toast.success(message);
  };

  const handleSuccess = () => {
    onActionSuccess();
    // Keep user on details tab to see updated state
    setActiveTab("details");
  };

  const runAction = async (action: "deploy" | "health") => {
    setActionLoading(action);
    setActionResult("");
    setTechnicalDetail("");
    try {
      if (action === "deploy") {
        await deployRegistryVersion(version.id);
        setActionResult(
          t("versionDetail.deployAccepted"),
        );
        toast.success(t("versionDetail.deployStarted"));
      } else {
        const result = await checkRegistryVersionHealth(version.id);
        const health = result.health as
          | {
              message?: string;
              reason_code?: string;
              technical_detail?: string;
            }
          | undefined;
        const message =
          result.endpoint_status === "healthy"
            ? t("versionDetail.endpointHealthy")
            : endpointActionMessage(
                {
                  message: result.message || health?.message,
                  reason_code: result.reason_code || health?.reason_code,
                  endpoint_error: result.endpoint_error,
                  success: false,
                },
                {
                  notReachable: t("versionDetail.endpointNotReachable"),
                  failed: t("versionDetail.endpointActionFailed"),
                  completed: t("versionDetail.endpointActionCompleted"),
                },
              );
        setActionResult(message);
        setTechnicalDetail(
          String(result.technical_detail || health?.technical_detail || ""),
        );
        toast[result.endpoint_status === "healthy" ? "success" : "warning"](
          message,
        );
      }
      handleSuccess();
    } catch (error) {
      const message = getApiErrorMessage(
        error,
        t("versionDetail.actionFailed", { action }),
      );
      setActionResult(message);
      toast.error(message);
    } finally {
      setActionLoading(null);
    }
  };

  const runSmokeTest = async () => {
    setActionLoading("smoke");
    setActionResult("");
    setSmokeResult(null);
    setTechnicalDetail("");
    try {
      const parsed = JSON.parse(smokePayload) as {
        features?: Record<string, unknown>;
      };
      if (
        !parsed ||
        typeof parsed !== "object" ||
        !parsed.features ||
        typeof parsed.features !== "object"
      ) {
        throw new Error(t("versionDetail.smokeFeaturesRequired"));
      }
      const result = await smokeTestRegistryVersion(version.id, {
        features: parsed.features,
      });
      setSmokeResult(result);
      if (result.success === false) {
        const message = endpointActionMessage(result, {
          notReachable: t("versionDetail.endpointNotReachable"),
          failed: t("versionDetail.endpointActionFailed"),
          completed: t("versionDetail.endpointActionCompleted"),
        });
        setActionResult(message);
        setTechnicalDetail(result.technical_detail || "");
        toast.warning(message);
      } else {
        toast.success(t("versionDetail.smokeTestCompleted"));
      }
    } catch (error) {
      const message =
        error instanceof SyntaxError
          ? t("versionDetail.smokeJsonInvalid")
          : getApiErrorMessage(
              error,
              error instanceof Error ? error.message : t("versionDetail.smokeFailed"),
            );
      setActionResult(message);
      toast.error(message);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="flex flex-col border border-border rounded-surface bg-surface shadow-sm overflow-hidden">
      {/* Tab Navigation */}
      <div className="flex border-b border-border bg-muted px-4 pt-3">
        {(["details", "insights", "metrics", "history"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-style-body-strong capitalize border-b-2 transition-colors ${
              activeTab === tab
                ? "border-primary text-color-primary"
                : "border-transparent text-color-muted-foreground hover:text-color-foreground hover:border-border"
            }`}
          >
            {t(
              {
                details: "summary",
                insights: "insights",
                metrics: "metrics",
                history: "history",
              }[tab],
            )}
          </button>
        ))}
        <div className="flex-1"></div>
      </div>

      <div className="p-6">
        {activeTab === "details" && (
          <div className="flex flex-col gap-6">
            {/* A. Version Control Header */}
            <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
              <div>
                <h3 className="text-style-display font-bold text-color-foreground flex items-center gap-3">
                  {family.display_name || family.name}
                  <span className="text-style-heading text-color-muted-foreground font-semibold px-2 py-0.5 rounded-compact border border-border bg-surface shadow-sm">
                    {formatVersion(version.version)}
                  </span>
                  {isProd && (
                    <span className="rounded-compact bg-success px-2.5 py-0.5 text-style-overline uppercase text-color-success-foreground shadow-sm">
                      {t("versionDetail.productionActiveLabel")}
                    </span>
                  )}
                  {!isProd && (
                    <span className="bg-muted text-color-muted-foreground text-style-caption px-2.5 py-0.5 rounded-compact uppercase font-bold">
                      {version.stage}
                    </span>
                  )}
                </h3>
                <p className="text-style-body text-color-muted-foreground mt-2 font-medium">
                  {t("versionDetail.sourceLabel")}{" "}
                  {version.source_type.replace("_", " ")}{" "}
                  {version.source_training_job_id
                    ? `· Job ID: ${version.source_training_job_id}`
                    : ""}
                </p>
              </div>

              {/* B. Action Row */}
              <div className="flex flex-wrap gap-2 md:gap-3">
                <Button
                  size="md"
                  variant="secondary"
                  icon={<GitCompare className="h-4 w-4" />}
                  onClick={() => setIsCompareModalOpen(true)}
                >
                  {t("versionDetail.compare")}
                </Button>

                {version.endpoint_url && (
                  <Button
                    size="md"
                    variant="secondary"
                    icon={<ExternalLink className="h-4 w-4" />}
                    onClick={() =>
                      window.open(`/dashboard/home/model-testing`, "_blank")
                    }
                  >
                    {t("versionDetail.testPredictions")}
                  </Button>
                )}

                <Button
                  size="md"
                  variant="secondary"
                  icon={<RotateCcw className="h-4 w-4" />}
                  disabled={isProd}
                  onClick={() => setIsRollbackModalOpen(true)}
                  title={
                    isProd
                      ? t("versionDetail.rollbackActiveTitle")
                      : t("versionDetail.rollbackTitle")
                  }
                >
                  {t("versionDetail.rollback")}
                </Button>

                {isProd ? (
                  <div className="flex items-center px-4 py-2 text-style-body-strong text-color-success bg-success-subtle border border-success/20 rounded-surface">
                    {t("versionDetail.productionActive")}
                  </div>
                ) : (
                  <Button
                    size="md"
                    variant="primary"
                    icon={<ArrowUpCircle className="h-4 w-4" />}
                    disabled={!canPromote}
                    onClick={() => setIsPromoteModalOpen(true)}
                    title={
                      !canPromote
                        ? t("versionDetail.promoteRequiresDeploy")
                        : t("versionDetail.promoteTitle")
                    }
                  >
                    {t("versionDetail.promoteAlias")}
                  </Button>
                )}
              </div>
            </div>

            {/* C. Production Semantics Callout */}
            {isProd && (
              <div className="bg-success-subtle border border-success/20 rounded-surface p-4 flex flex-col gap-1 text-color-success">
                <div className="text-style-body">
                  <strong>{t("versionDetail.productionMarkerActive")}</strong>{" "}
                  {t("versionDetail.stableRoutingNote")}
                </div>
                <div className="text-style-caption text-color-success/80">
                  {t("versionDetail.versionEndpointNote")}
                </div>
              </div>
            )}

            <div className="grid lg:grid-cols-2 gap-6">
              <div className="flex flex-col gap-4 bg-surface border border-border rounded-surface p-5 shadow-sm">
                <h4 className="text-style-body-strong text-color-foreground uppercase flex items-center justify-between border-b border-border pb-2">
                  <span className="inline-flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-color-info" />
                    {t("versionDetail.tracking.title")}
                  </span>
                  <span
                    className={classNames(
                      "text-style-caption px-2 py-0.5 rounded-full font-bold uppercase border",
                      trackingBadge(version.tracking_status),
                    )}
                  >
                    {t(trackingLabelKey(version.tracking_status))}
                  </span>
                </h4>
                <p className="text-style-body text-color-muted-foreground">
                  {t(trackingDescriptionKey(version.tracking_status))}
                </p>
                {version.tracking_status === "completed" && (
                  <div className="rounded-surface border border-success/20 bg-success-subtle p-3 text-style-body text-color-success">
                    {t("versionDetail.tracking.completedNotice")}
                  </div>
                )}
                {version.tracking_status === "skipped" && (
                  <div className="rounded-surface border border-primary/20 bg-primary-subtle p-3 text-style-body text-color-primary">
                    {t("versionDetail.tracking.disabledNotice")}
                  </div>
                )}
                {version.tracking_status === "failed" && (
                  <div className="rounded-surface border border-warning/20 bg-warning-subtle p-3 text-style-body text-color-warning">
                    {t("versionDetail.tracking.retainedNotice")}
                  </div>
                )}
                {version.tracking_ingested_at && (
                  <div>
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                      {t("versionDetail.tracking.ingestedAt")}
                    </p>
                    <p className="text-style-body text-color-foreground font-medium">
                      {new Date(version.tracking_ingested_at).toLocaleString()}
                    </p>
                  </div>
                )}
                {version.tracking_error && (
                  <div className="rounded-surface border border-warning/20 bg-warning-subtle p-3 text-style-body text-color-warning">
                    {version.tracking_error}
                  </div>
                )}
                {version.mlflow_run_id && (
                  <div>
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                      {t("versionDetail.tracking.internalRun")}
                    </p>
                    <code className="font-mono text-style-code-sm text-color-foreground bg-muted border border-border px-2 py-1 rounded-compact break-all block select-all">
                      {version.mlflow_run_id}
                    </code>
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-4 bg-surface border border-border rounded-surface p-5 shadow-sm">
                <h4 className="text-style-body-strong text-color-foreground uppercase flex items-center justify-between border-b border-border pb-2">
                  {t("versionDetail.deployability")}
                  <span
                    className={classNames(
                      "text-style-caption px-2 py-0.5 rounded-full font-bold uppercase border",
                      deployabilityBadge(version.deployability_status),
                    )}
                  >
                    {version.deployability_status ||
                      t("versionDetail.unknown")}
                  </span>
                </h4>
                <p className="text-style-body text-color-muted-foreground">
                  {version.deployability_reason ||
                    t("versionDetail.deployabilityUnknown")}
                </p>
                <div className="grid grid-cols-2 gap-3 text-style-body">
                  <div className="rounded-surface bg-muted border border-border p-3">
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                      {t("versionDetail.artifacts")}
                    </p>
                    <p className="text-style-section-title font-bold text-color-foreground">
                      {artifactEntries.length}
                    </p>
                  </div>
                  <div className="rounded-surface bg-muted border border-border p-3">
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                      {t("versionDetail.metrics")}
                    </p>
                    <p className="text-style-section-title font-bold text-color-foreground">
                      {metricEntries.length}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-5 bg-surface border border-border rounded-surface p-5 shadow-sm">
              <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 border-b border-border pb-4">
                <div>
                  <h4 className="text-style-body-strong text-color-foreground uppercase flex items-center gap-2">
                    <Rocket className="h-4 w-4 text-color-info" />
                    {t("versionDetail.deploymentActions")}
                  </h4>
                  <p className="mt-2 text-style-body text-color-muted-foreground max-w-3xl">
                    {t("versionDetail.deploymentActionsDescription")}
                  </p>
                </div>
                <span
                  className={classNames(
                    "text-style-caption px-2 py-0.5 rounded-full font-bold uppercase border self-start",
                    deployabilityBadge(version.deployability_status),
                  )}
                >
                  {version.deployability_status || t("versionDetail.unknown")}
                </span>
              </div>

              <div className="flex flex-col gap-5">
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    size="md"
                    variant="primary"
                    icon={<Rocket className="h-4 w-4" />}
                    disabled={!version.can_deploy || actionLoading !== null}
                    onClick={() => void runAction("deploy")}
                    title={
                      !version.can_deploy
                        ? version.deploy_disabled_reason
                        : t("versionDetail.deployEndpoint")
                    }
                  >
                    {actionLoading === "deploy"
                      ? t("versionDetail.deploying")
                      : t("versionDetail.deploy")}
                  </Button>
                  <Button
                    size="md"
                    variant="secondary"
                    icon={<HeartPulse className="h-4 w-4" />}
                    disabled={!version.endpoint_url || actionLoading !== null}
                    onClick={() => void runAction("health")}
                    title={
                      !version.endpoint_url
                        ? t("versionDetail.deployBeforeHealth")
                        : t("versionDetail.checkHealth")
                    }
                  >
                    {actionLoading === "health"
                      ? t("versionDetail.checking")
                      : t("versionDetail.checkHealthAction")}
                  </Button>
                  <Button
                    size="md"
                    variant="secondary"
                    icon={<Play className="h-4 w-4" />}
                    disabled={!version.endpoint_url || actionLoading !== null}
                    onClick={() => void runSmokeTest()}
                    title={
                      !version.endpoint_url
                        ? t("versionDetail.deployBeforeSmoke")
                        : t("versionDetail.runSmoke")
                    }
                  >
                    {actionLoading === "smoke"
                      ? t("versionDetail.running")
                      : t("versionDetail.runSmoke")}
                  </Button>
                </div>

                {!version.can_deploy && (
                  <div className="rounded-surface border border-warning/20 bg-warning-subtle p-3 text-style-body text-color-warning">
                    {version.deploy_disabled_reason ||
                      version.deployability_reason ||
                      t("versionDetail.cannotDeploy")}
                  </div>
                )}

                <div className="grid gap-3 text-style-body md:grid-cols-3">
                  <div className="rounded-surface bg-muted border border-border p-4">
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                      {t("versionDetail.buildStatus")}
                    </p>
                    <p className="font-semibold text-color-foreground">
                      {version.build_status || "-"}
                    </p>
                  </div>
                  <div className="rounded-surface bg-muted border border-border p-4">
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                      {t("versionDetail.endpointStatus")}
                    </p>
                    <p className="font-semibold text-color-foreground">
                      {version.endpoint_status ||
                        version.deployment_status ||
                        "-"}
                    </p>
                  </div>
                  <div className="rounded-surface bg-muted border border-border p-4">
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                      {t("versionDetail.deployability")}
                    </p>
                    <p className="font-semibold text-color-foreground">
                      {version.deployability_status ||
                        t("versionDetail.unknown")}
                    </p>
                  </div>
                </div>

                {(version.build_error ||
                  version.endpoint_error ||
                  actionResult) && (
                  <div className="rounded-surface border border-border bg-muted p-4 text-style-body text-color-foreground break-words">
                    <p>
                      {actionResult ||
                        version.endpoint_error ||
                        version.build_error}
                    </p>
                    {technicalDetail && (
                      <details className="mt-3 rounded-compact border border-border bg-surface p-2 text-style-caption text-color-muted-foreground">
                        <summary className="cursor-pointer font-semibold text-color-muted-foreground">
                          {t("versionDetail.technicalDetail")}
                        </summary>
                        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono">
                          {technicalDetail}
                        </pre>
                      </details>
                    )}
                  </div>
                )}

                <div className="rounded-surface border border-border bg-muted/60 p-4">
                  <div className="mb-3">
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase">
                      {t("versionDetail.smokeTest")}
                    </p>
                    <p className="text-style-caption text-color-muted-foreground mt-1">
                      {t("versionDetail.smokeSchemaHint")}
                    </p>
                  </div>
                  <div className="grid gap-4 2xl:grid-cols-2">
                    <textarea
                      value={smokePayload}
                      onChange={(event) => setSmokePayload(event.target.value)}
                      className="min-h-40 w-full rounded-control border border-terminal-border bg-terminal p-3 font-mono text-style-code-sm text-color-terminal-foreground outline-none focus:border-terminal-info focus:ring-2 focus:ring-ring"
                      spellCheck={false}
                    />
                    <div className="min-h-40 rounded-surface border border-border bg-surface p-3">
                      <p className="mb-2 text-style-overline uppercase text-color-muted-foreground">
                        {t("versionDetail.response")}
                      </p>
                      {smokeResult !== null ? (
                        <pre className="max-h-72 overflow-auto rounded-surface border border-terminal-border bg-terminal p-3 text-style-caption text-color-terminal-foreground">
                          {JSON.stringify(
                            withoutTechnicalDetail(smokeResult),
                            null,
                            2,
                          )}
                        </pre>
                      ) : (
                        <div className="flex min-h-28 items-center justify-center rounded-surface border border-dashed border-border bg-muted text-style-body text-color-muted-foreground">
                          {t("versionDetail.smokePrompt")}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid xl:grid-cols-3 gap-6">
              <div className="flex flex-col gap-3 bg-surface border border-border rounded-surface p-5 shadow-sm">
                <h4 className="text-style-body-strong text-color-foreground uppercase flex items-center gap-2 border-b border-border pb-2">
                  <Gauge className="h-4 w-4 text-color-success" />
                  {t("versionDetail.metrics")}
                </h4>
                {metricEntries.length > 0 ? (
                  <div className="grid gap-2">
                    {metricEntries.map(([name, value]) => (
                      <div
                        key={name}
                        className="flex items-center justify-between gap-3 rounded-surface bg-muted px-3 py-2"
                      >
                        <span
                          className="text-style-body-strong text-color-muted-foreground truncate"
                          title={name}
                        >
                          {name}
                        </span>
                        <span className="font-mono text-style-code-sm font-semibold text-color-foreground">
                          {formatValue(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-style-body text-color-muted-foreground">
                    {t("versionDetail.noMetrics")}
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-3 bg-surface border border-border rounded-surface p-5 shadow-sm">
                <h4 className="text-style-body-strong text-color-foreground uppercase flex items-center gap-2 border-b border-border pb-2">
                  <SlidersHorizontal className="h-4 w-4 text-color-chart-3" />
                  {t("versionDetail.params")}
                </h4>
                {paramEntries.length > 0 ? (
                  <div className="grid gap-2">
                    {paramEntries.map(([name, value]) => (
                      <div
                        key={name}
                        className="flex items-start justify-between gap-3 rounded-surface bg-muted px-3 py-2"
                      >
                        <span className="text-style-body-strong text-color-muted-foreground break-all">
                          {name}
                        </span>
                        <span className="font-mono text-style-code-sm text-color-foreground text-right break-all">
                          {formatValue(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-style-body text-color-muted-foreground">
                    {t("versionDetail.noParams")}
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-3 bg-surface border border-border rounded-surface p-5 shadow-sm">
                <h4 className="text-style-body-strong text-color-foreground uppercase flex items-center gap-2 border-b border-border pb-2">
                  <FileText className="h-4 w-4 text-color-muted-foreground" />
                  {t("versionDetail.sourceTrainingJob")}
                </h4>
                {version.source_training_job_id ? (
                  <div className="grid gap-3 text-style-body">
                    <div>
                      <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                        {t("versionDetail.job")}
                      </p>
                      <a
                        href={`/dashboard/model-training/${version.source_training_job_id}`}
                        className="font-semibold text-color-info hover:text-color-info-hover"
                      >
                        #{version.source_training_job_id}{" "}
                        {version.source_training_job_name || ""}
                      </a>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                          {t("versionDetail.status")}
                        </p>
                        <p className="font-medium text-color-foreground">
                          {version.source_training_job_status || "-"}
                        </p>
                      </div>
                      <div>
                        <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                          {t("versionDetail.backend")}
                        </p>
                        <p className="font-medium text-color-foreground">
                          {version.source_training_job_backend || "-"}
                        </p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-style-body text-color-muted-foreground">
                    {t("versionDetail.notTrainingSource")}
                  </p>
                )}
              </div>
            </div>

            <div className="flex flex-col gap-3 bg-surface border border-border rounded-surface p-5 shadow-sm">
              <h4 className="text-style-body-strong text-color-foreground uppercase border-b border-border pb-2">
                {t("versionDetail.artifactWeights")}
              </h4>
              {artifactEntries.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-border text-style-body">
                    <thead className="bg-muted text-style-caption uppercase text-color-muted-foreground">
                      <tr>
                        <th className="px-3 py-2 text-left font-semibold">
                          {t("versionDetail.path")}
                        </th>
                        <th className="px-3 py-2 text-left font-semibold">
                          {t("versionDetail.kind")}
                        </th>
                        <th className="px-3 py-2 text-right font-semibold">
                          {t("versionDetail.size")}
                        </th>
                        <th className="px-3 py-2 text-left font-semibold">
                          {t("versionDetail.sha256")}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {artifactEntries.map((item, index) => (
                        <tr key={`${item.path}-${index}`}>
                          <td className="px-3 py-2 font-mono text-style-code-sm text-color-foreground break-all">
                            {item.path}
                          </td>
                          <td className="px-3 py-2">
                            <span className="rounded-full bg-muted px-2 py-0.5 text-style-caption-strong text-color-foreground">
                              {item.kind || t("versionDetail.otherArtifact")}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-style-code-sm text-color-muted-foreground">
                            {formatBytes(item.size_bytes)}
                          </td>
                          <td className="px-3 py-2 font-mono text-style-code-sm text-color-muted-foreground">
                            {item.sha256
                              ? `${item.sha256.slice(0, 12)}...`
                              : "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-style-body text-color-muted-foreground">
                  {t("versionDetail.noArtifactManifest")}
                </p>
              )}
            </div>

            {/* F. Drift Summary Card */}
            <DriftSummaryCard
              driftSummary={version.drift_summary || version.driftSummary}
              modelProjectId={version.project_id}
            />

            <div className="flex flex-col gap-3 bg-surface border border-border rounded-surface p-5 shadow-sm">
              <h4 className="text-style-body-strong text-color-foreground uppercase flex items-center justify-between border-b border-border pb-2">
                <span className="inline-flex items-center gap-2">
                  <Terminal className="h-4 w-4 text-color-info" />
                  {t("versionDetail.routingAliases")}
                </span>
                <span className="rounded-full border border-info-border bg-info-subtle px-2 py-0.5 text-style-caption font-bold uppercase text-color-info">
                  {t("versionDetail.apiProxy")}
                </span>
              </h4>
              {routingAliases.length > 0 ? (
                <div className="grid gap-3">
                  {routingAliases.map((alias) => {
                    const aliasName =
                      alias.alias_name || alias.aliasName || "alias";
                    const endpointUrl =
                      alias.endpoint_url || alias.endpointUrl || "";
                    const promotedAt = alias.promoted_at || alias.promotedAt;
                    return (
                      <div
                        key={`${aliasName}-${endpointUrl}`}
                        className="rounded-surface border border-border bg-muted p-4"
                      >
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="rounded-full bg-info-subtle px-2.5 py-1 text-style-overline uppercase text-color-info">
                                {aliasName}
                              </span>
                              <span className="rounded-full bg-success-subtle px-2.5 py-1 text-style-overline uppercase text-color-success">
                                {alias.status || t("versionDetail.active")}
                              </span>
                            </div>
                            <code className="mt-3 block break-all rounded-compact border border-border bg-surface px-3 py-2 font-mono text-style-code-sm text-color-foreground">
                              {endpointUrl || t("versionDetail.aliasUnavailable")}
                            </code>
                            {promotedAt && (
                              <p className="mt-2 text-style-caption text-color-muted-foreground">
                                {t("versionDetail.promotedAt")}{" "}
                                {new Date(promotedAt).toLocaleString()}
                              </p>
                            )}
                          </div>
                          {endpointUrl && (
                            <Button
                              size="sm"
                              variant="secondary"
                              icon={<Copy className="h-3.5 w-3.5" />}
                              onClick={() =>
                                void copyText(
                                  endpointUrl,
                                  t("versionDetail.aliasCopied"),
                                )
                              }
                            >
                              {t("versionDetail.copy")}
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-style-body text-color-muted-foreground">
                  {t("versionDetail.noAlias")}
                </p>
              )}
            </div>

            <div className="grid md:grid-cols-2 gap-6 mt-2">
              {/* D. Deployment Info */}
              <div className="flex flex-col gap-4 bg-surface border border-border rounded-surface p-5 shadow-sm">
                <h4 className="text-style-body-strong text-color-foreground uppercase flex items-center justify-between border-b border-border pb-2">
                  {t("versionDetail.deploymentInfo")}
                  {version.endpoint_url ? (
                    <span className="text-style-caption bg-primary-subtle text-color-primary px-2 py-0.5 rounded-full font-bold uppercase">
                      {t("versionDetail.ready")}
                    </span>
                  ) : (
                    <span className="text-style-caption bg-muted text-color-muted-foreground px-2 py-0.5 rounded-full font-bold uppercase">
                      {t("versionDetail.noEndpoint")}
                    </span>
                  )}
                </h4>

                <div>
                  <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                    {t("versionDetail.imageName")}
                  </p>
                  <p className="font-mono text-style-code-sm text-color-foreground break-all">
                    {version.image_name || t("versionDetail.notAvailable")}
                  </p>
                </div>

                <div>
                  <p className="text-style-caption-strong text-color-muted-foreground uppercase flex items-center gap-2 mb-1">
                    <Terminal className="h-3 w-3" />{" "}
                    {t("versionDetail.endpointUrl")}
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="font-mono text-style-code-sm text-color-foreground bg-muted border border-border px-3 py-2 rounded-compact flex-1 truncate select-all">
                      {version.endpoint_url || t("versionDetail.notAvailable")}
                    </code>
                    {version.endpoint_url && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={copyEndpoint}
                        className="shrink-0 flex items-center gap-1.5 px-3 py-2 border border-border"
                      >
                        {copied ? (
                          <Check className="h-3.5 w-3.5 text-color-success" />
                        ) : (
                          <Copy className="h-3.5 w-3.5 text-color-muted-foreground" />
                        )}
                        <span
                          className={
                            copied ? "text-color-success" : "text-color-foreground"
                          }
                        >
                          {copied
                            ? t("versionDetail.copied")
                            : t("versionDetail.copy")}
                        </span>
                      </Button>
                    )}
                  </div>
                </div>
              </div>

              {/* E. Artifact Info */}
              <div className="flex flex-col gap-4 bg-surface border border-border rounded-surface p-5 shadow-sm">
                <h4 className="text-style-body-strong text-color-foreground uppercase border-b border-border pb-2">
                  {t("versionDetail.artifactInfo")}
                </h4>

                <div>
                  <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                    {t("versionDetail.artifactUri")}
                  </p>
                  <p className="font-mono text-style-code-sm text-color-foreground break-all">
                    {version.artifact_uri || t("versionDetail.notAvailable")}
                  </p>
                </div>

                {/* Optional internal MLflow lineage. Native Registry remains the primary product flow. */}
                <div className="border-t border-border pt-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase">
                      {t("versionDetail.mlflowRun")}
                    </p>
                    {version.mlflow_run_url ? (
                      <a
                        href={version.mlflow_run_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 text-style-caption-strong text-color-primary hover:text-color-primary-hover bg-primary-subtle border border-primary/20 px-3 py-1 rounded-full transition-colors"
                        title={t("versionDetail.openMlflow")}
                      >
                        <ExternalLink className="h-3 w-3" />
                        {t("versionDetail.openMlflowAction")}
                      </a>
                    ) : null}
                  </div>

                  {version.mlflow_run_id ? (
                    <div className="flex flex-col gap-2">
                      <div>
                        <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-0.5">
                          {t("versionDetail.runId")}
                        </p>
                        <code className="font-mono text-style-code-sm text-color-foreground bg-muted border border-border px-2 py-1 rounded-compact break-all block select-all">
                          {version.mlflow_run_id}
                        </code>
                      </div>
                      {version.mlflow_model_uri && (
                        <div>
                          <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-0.5">
                            {t("versionDetail.modelUri")}
                          </p>
                          <code className="font-mono text-style-code-sm text-color-foreground bg-muted border border-border px-2 py-1 rounded-compact break-all block">
                            {version.mlflow_model_uri}
                          </code>
                        </div>
                      )}
                      <p className="text-style-caption text-color-muted-foreground mt-1">
                        {t("versionDetail.nativeRegistryDescription")}{" "}
                        <span className="font-medium text-color-warning">
                          {t("versionDetail.mlflowOptional")}
                        </span>
                      </p>
                    </div>
                  ) : (
                    <div className="bg-muted border border-dashed border-border rounded-surface p-3 flex flex-col gap-1">
                      <p className="text-style-caption-strong text-color-muted-foreground">
                        {t("versionDetail.noMlflowRun")}
                      </p>
                      <p className="text-style-caption text-color-muted-foreground">
                        {t("versionDetail.nativeRegistryFallback")}
                      </p>
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-4 mt-2">
                  <div>
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                      {t("versionDetail.created")}
                    </p>
                    <p className="text-style-body text-color-foreground font-medium">
                      {new Date(version.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div>
                    <p className="text-style-caption-strong text-color-muted-foreground uppercase mb-1">
                      {t("versionDetail.updated")}
                    </p>
                    <p className="text-style-body text-color-foreground font-medium">
                      {new Date(version.updated_at).toLocaleString()}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "insights" && (
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-2">
              <h3 className="text-style-page-title font-bold text-color-foreground flex items-center gap-3">
                <BarChart3 className="h-6 w-6 text-color-chart-1" />
                {t("versionDetail.insightsTitle")}
              </h3>
              <p className="text-style-body text-color-muted-foreground max-w-3xl">
                {t("versionDetail.insightsDescription")}
              </p>
            </div>

            {insightItems.length === 0 ? (
              <div className="rounded-surface border border-dashed border-border bg-muted p-8 text-center">
                <BarChart3 className="mx-auto h-10 w-10 text-color-muted-foreground" />
                <h4 className="mt-3 text-style-heading text-color-foreground">
                  {t("versionDetail.noInsights")}
                </h4>
                <p className="mt-2 text-style-body text-color-muted-foreground">
                  {t("versionDetail.insightsHint")}
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-6">
                <div className="grid gap-3 md:grid-cols-4">
                  <div className="rounded-surface border border-border bg-surface p-4 shadow-sm">
                    <p className="text-style-overline uppercase text-color-muted-foreground">
                      {t("versionDetail.kind")}
                    </p>
                    <p className="mt-1 text-style-body-strong capitalize text-color-foreground">
                      {insightKind.replace("_", " ")}
                    </p>
                  </div>
                  <div className="rounded-surface border border-border bg-surface p-4 shadow-sm">
                    <p className="text-style-overline uppercase text-color-muted-foreground">
                      {t("versionDetail.items")}
                    </p>
                    <p className="mt-1 text-style-body-strong text-color-foreground">
                      {insightItemCount}
                    </p>
                  </div>
                  <div className="rounded-surface border border-border bg-surface p-4 shadow-sm">
                    <p className="text-style-overline uppercase text-color-muted-foreground">
                      {t("versionDetail.topFeature")}
                    </p>
                    <p
                      className="mt-1 truncate text-style-body-strong text-color-foreground"
                      title={topInsightItem?.name}
                    >
                      {topInsightItem?.name || "-"}
                    </p>
                  </div>
                  <div className="rounded-surface border border-border bg-surface p-4 shadow-sm">
                    <p className="text-style-overline uppercase text-color-muted-foreground">
                      {t("versionDetail.source")}
                    </p>
                    <p className="mt-1 truncate text-style-body-strong text-color-foreground">
                      {modelInsights.source ||
                        t("versionDetail.trainingArtifact")}
                    </p>
                  </div>
                </div>

                <div className="rounded-surface border border-border bg-surface p-5 shadow-sm">
                  <div className="flex items-start justify-between gap-4 border-b border-border pb-3">
                    <div>
                      <h4 className="text-style-overline uppercase text-color-foreground">
                        {insightKind === "coefficients"
                          ? t("versionDetail.topCoefficients")
                          : t("versionDetail.topFeatureImportance")}
                      </h4>
                      <p className="mt-1 text-style-caption text-color-muted-foreground">
                        {t("versionDetail.showingItems", {
                          shown: topInsightItems.length,
                          total:
                            modelInsights.feature_count || insightItems.length,
                        })}
                      </p>
                    </div>
                    <span className="rounded-full border border-primary/20 bg-primary-subtle px-2.5 py-1 text-style-caption font-bold uppercase text-color-primary">
                      {insightKind.replace("_", " ")}
                    </span>
                  </div>

                  <div className="mt-5 flex flex-col gap-4">
                    {topInsightItems.map((item) => {
                      const magnitude = item.abs_value ?? Math.abs(item.value);
                      const width =
                        maxInsightAbs > 0
                          ? Math.max(3, (magnitude / maxInsightAbs) * 100)
                          : 0;
                      const negative = item.value < 0;
                      return (
                        <div
                          key={`${item.rank || item.name}-${item.name}-${item.class_name || ""}`}
                          className="grid items-center gap-3 md:grid-cols-[minmax(160px,260px)_1fr_96px]"
                        >
                          <div className="min-w-0">
                            <p
                              className="truncate text-style-body-strong text-color-foreground"
                              title={item.name}
                            >
                              {item.name}
                            </p>
                            {item.class_name && (
                              <p className="truncate text-style-caption text-color-muted-foreground">
                                {item.class_name}
                              </p>
                            )}
                          </div>
                          <div className="h-6 overflow-hidden rounded-compact bg-muted ring-1 ring-border">
                            <div
                              className={classNames(
                                "h-6 rounded-compact shadow-sm",
                                negative ? "bg-danger" : "bg-chart-1",
                              )}
                              style={{ width: `${width}%` }}
                            />
                          </div>
                          <p className="text-right font-mono text-style-code-sm-strong text-color-foreground">
                            {formatInsightValue(item.value)}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="rounded-surface border border-border bg-surface p-5 shadow-sm">
                  <h4 className="border-b border-border pb-3 text-style-overline uppercase text-color-foreground">
                    {t("versionDetail.insightTable")}
                  </h4>
                  <div className="mt-4 max-h-[560px] overflow-auto">
                    <table className="min-w-full divide-y divide-border text-style-body">
                      <thead className="sticky top-0 z-10 bg-muted text-style-caption uppercase text-color-muted-foreground">
                        <tr>
                          <th className="px-3 py-2 text-right font-semibold">
                            {t("versionDetail.rank")}
                          </th>
                          <th className="px-3 py-2 text-left font-semibold">
                            {t("versionDetail.feature")}
                          </th>
                          {insightKind === "coefficients" && (
                            <th className="px-3 py-2 text-left font-semibold">
                              {t("versionDetail.class")}
                            </th>
                          )}
                          <th className="px-3 py-2 text-right font-semibold">
                            {insightKind === "coefficients"
                              ? t("versionDetail.coefficient")
                              : t("versionDetail.importance")}
                          </th>
                          <th className="px-3 py-2 text-right font-semibold">
                            {t("versionDetail.absolute")}
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {insightItems.slice(0, 500).map((item, index) => (
                          <tr
                            key={`${item.name}-${item.class_name || ""}-${index}`}
                            className="hover:bg-muted"
                          >
                            <td className="px-3 py-2 text-right font-mono text-style-code-sm text-color-muted-foreground">
                              {item.rank || index + 1}
                            </td>
                            <td className="px-3 py-2 font-medium text-color-foreground">
                              {item.name}
                            </td>
                            {insightKind === "coefficients" && (
                              <td className="px-3 py-2 text-color-muted-foreground">
                                {item.class_name || "-"}
                              </td>
                            )}
                            <td className="px-3 py-2 text-right font-mono text-style-code-sm text-color-foreground">
                              {formatInsightValue(item.value)}
                            </td>
                            <td className="px-3 py-2 text-right font-mono text-style-code-sm text-color-muted-foreground">
                              {formatInsightValue(
                                item.abs_value ?? Math.abs(item.value),
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === "metrics" && (
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-2">
              <h3 className="text-style-page-title font-bold text-color-foreground flex items-center gap-3">
                <Gauge className="h-6 w-6 text-color-success" />
                {t("versionDetail.metrics")}
              </h3>
              <p className="text-style-body text-color-muted-foreground max-w-3xl">
                {t("versionDetail.metricsDescription")}
              </p>
            </div>

            {metricEntries.length > 0 ? (
              <>
                {scalarMetricEntries.length > 0 && (
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                    {scalarMetricEntries.slice(0, 8).map(([name, value]) => (
                      <div
                        key={`summary-${name}`}
                        className="rounded-surface border border-border bg-surface p-4 shadow-sm"
                      >
                        <p
                          className="truncate text-style-overline uppercase text-color-muted-foreground"
                          title={name}
                        >
                          {name.replace(/_/g, " ")}
                        </p>
                        <p
                          className="mt-2 truncate font-mono text-style-page-title font-bold text-color-foreground"
                          title={formatValue(value)}
                        >
                          {shortValue(value, 36)}
                        </p>
                      </div>
                    ))}
                  </div>
                )}

                {numericMetricEntries.length > 0 && (
                  <div className="rounded-surface border border-border bg-surface p-5 shadow-sm">
                    <h4 className="border-b border-border pb-3 text-style-overline uppercase text-color-foreground">
                      {t("versionDetail.metricOverview")}
                    </h4>
                    <div className="mt-5 flex flex-col gap-3">
                      {numericMetricEntries.map((entry) => {
                        const magnitude = Math.abs(entry.numericValue);
                        const width =
                          maxMetricAbs > 0
                            ? Math.max(3, (magnitude / maxMetricAbs) * 100)
                            : 0;
                        const negative = entry.numericValue < 0;
                        return (
                          <div
                            key={`metric-bar-${entry.name}`}
                            className="grid items-center gap-3 md:grid-cols-[minmax(160px,260px)_1fr_96px]"
                          >
                            <p
                              className="truncate text-style-body-strong text-color-foreground"
                              title={entry.name}
                            >
                              {entry.name.replace(/_/g, " ")}
                            </p>
                            <div className="h-5 overflow-hidden rounded-compact bg-muted ring-1 ring-border">
                              <div
                                className={classNames(
                                  "h-5 rounded-compact shadow-sm",
                                  negative ? "bg-danger" : "bg-success",
                                )}
                                style={{ width: `${width}%` }}
                              />
                            </div>
                            <p className="text-right font-mono text-style-code-sm-strong text-color-foreground">
                              {formatValue(entry.value)}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div className="rounded-surface border border-border bg-surface p-5 shadow-sm">
                  <h4 className="border-b border-border pb-3 text-style-overline uppercase text-color-foreground">
                    {t("versionDetail.metricTable")}
                  </h4>
                  <div className="mt-4 overflow-auto">
                    <table className="min-w-full divide-y divide-border text-style-body">
                      <thead className="bg-muted text-style-caption uppercase text-color-muted-foreground">
                        <tr>
                          <th className="px-3 py-2 text-left font-semibold">
                            {t("versionDetail.metric")}
                          </th>
                          <th className="px-3 py-2 text-right font-semibold">
                            {t("versionDetail.value")}
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {scalarMetricEntries.map(([name, value]) => (
                          <tr
                            key={`metric-row-${name}`}
                            className="hover:bg-muted"
                          >
                            <td className="px-3 py-2 font-medium text-color-foreground">
                              {name}
                            </td>
                            <td
                              className="px-3 py-2 text-right font-mono text-style-code-sm text-color-foreground"
                              title={formatValue(value)}
                            >
                              {shortValue(value, 120)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {objectMetricEntries.length > 0 && (
                  <div className="rounded-surface border border-border bg-surface p-5 shadow-sm">
                    <h4 className="border-b border-border pb-3 text-style-overline uppercase text-color-foreground">
                      {t("versionDetail.metricMetadata")}
                    </h4>
                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                      {objectMetricEntries.map(([name, value]) => (
                        <div
                          key={`metric-object-${name}`}
                          className="rounded-surface border border-border bg-muted p-4"
                        >
                          <p className="mb-2 text-style-overline uppercase text-color-muted-foreground">
                            {name.replace(/_/g, " ")}
                          </p>
                          {isPlainRecord(value) ? (
                            <dl className="grid gap-2">
                              {Object.entries(value)
                                .slice(0, 20)
                                .map(([key, item]) => (
                                  <div
                                    key={key}
                                    className="grid grid-cols-[minmax(120px,220px)_1fr] gap-3 text-style-body"
                                  >
                                    <dt
                                      className="truncate font-medium text-color-muted-foreground"
                                      title={key}
                                    >
                                      {key}
                                    </dt>
                                    <dd
                                      className="truncate font-mono text-color-foreground"
                                      title={formatValue(item)}
                                    >
                                      {shortValue(item, 90)}
                                    </dd>
                                  </div>
                                ))}
                            </dl>
                          ) : (
                            <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-compact bg-surface p-3 text-style-caption text-color-foreground">
                              {formatValue(value)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="rounded-surface border border-dashed border-border bg-muted p-8 text-center">
                <Gauge className="mx-auto h-10 w-10 text-color-muted-foreground" />
                <h4 className="mt-3 text-style-heading text-color-foreground">
                  {t("versionDetail.noVersionMetrics")}
                </h4>
                <p className="mt-2 text-style-body text-color-muted-foreground">
                  {t("versionDetail.metricsHint")}
                </p>
              </div>
            )}

            <div className="rounded-surface border border-border bg-surface p-5 shadow-sm">
              <div className="mb-4">
                <h4 className="text-style-overline uppercase text-color-foreground">
                  {t("versionDetail.metricHistory")}
                </h4>
                <p className="mt-1 text-style-caption text-color-muted-foreground">
                  {t("versionDetail.metricHistoryDescription")}
                </p>
              </div>
              <ModelMetricsPanel familyId={family.id} versionId={version.id} />
            </div>
          </div>
        )}

        {activeTab === "history" && (
          <ModelHistoryTimeline familyId={family.id} />
        )}
      </div>

      {isPromoteModalOpen && (
        <PromoteVersionModal
          family={family}
          version={version}
          onClose={() => setIsPromoteModalOpen(false)}
          onSuccess={() => {
            setIsPromoteModalOpen(false);
            handleSuccess();
          }}
        />
      )}

      {isRollbackModalOpen && (
        <RollbackVersionModal
          family={family}
          version={version}
          onClose={() => setIsRollbackModalOpen(false)}
          onSuccess={() => {
            setIsRollbackModalOpen(false);
            handleSuccess();
          }}
        />
      )}

      {isCompareModalOpen && (
        <VersionComparisonModal
          family={family}
          versions={allVersions}
          onClose={() => setIsCompareModalOpen(false)}
        />
      )}
    </div>
  );
}
