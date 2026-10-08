import {
  listProjectBuilds,
  listDeployments,
} from "@/features/deployments/api/deployApi";
import type { ModelProject } from "@/features/projects/types";
import { Badge } from "@/shared/components/Badge";
import { InfoItem } from "@/shared/components/InfoItem";
import { formatDateTime } from "@/shared/i18n/formatters";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

export interface InformationOverviewPageProps {
  model: ModelProject;
  onUpdateAccessMode?: (accessMode: "private" | "public") => void;
}

export function InformationOverviewPage({
  model,
}: InformationOverviewPageProps) {
  const { t, i18n } = useTranslation("overview");

  const buildHistory = useQuery({
    queryKey: ["deployments", "history", model.id],
    queryFn: () => listProjectBuilds(model.id),
    enabled: Boolean(model.id),
    staleTime: 10000,
  });

  const deployments = useQuery({
    queryKey: ["deployments", "all"],
    queryFn: listDeployments,
    staleTime: 10000,
  });

  const latestBuild = buildHistory.data?.[0];
  const latestDeployment =
    deployments.data?.find((d) => d.build_id === latestBuild?.id) ||
    deployments.data?.[0];

  // 1. Version
  const versionNumber =
    model.active_endpoint?.version_number ||
    latestBuild?.version_number ||
    model.version ||
    "1";

  // 2. Model Status (Lifecycle)
  const lifecycleStatus = model.lifecycle_status ?? "preview";
  const modelStatusTone =
    lifecycleStatus === "running"
      ? "success"
      : lifecycleStatus === "registered"
        ? "primary"
        : "neutral";

  // 3. Running Status
  const isRunning = Boolean(
    model.active_endpoint?.deployment_status === "succeeded" ||
      model.lifecycle_status === "running",
  );
  const isStopped =
    model.endpoint_status === "stopped" ||
    latestDeployment?.status === "stopped";
  const runningStatusLabel = isRunning
    ? t("workflow.running")
    : isStopped
      ? t("workflow.stopped")
      : t("workflow.notRunning");
  const runningStatusTone = isRunning
    ? "success"
    : "neutral";

  // 4. Build Status
  const rawBuildStatus =
    latestBuild?.status || (model.active_endpoint ? "ready" : undefined);
  const buildStatusLabel = rawBuildStatus
    ? t(`workflow.${rawBuildStatus}`, { defaultValue: rawBuildStatus })
    : t("workflow.notBuilt");
  const buildStatusTone =
    rawBuildStatus === "ready"
      ? "success"
      : rawBuildStatus === "building" ||
          rawBuildStatus === "queued" ||
          rawBuildStatus === "pending"
        ? "warning"
        : rawBuildStatus === "failed"
          ? "danger"
          : "neutral";

  // 5. Deployment Status
  const rawDeployStatus =
    model.active_endpoint?.deployment_status ||
    latestDeployment?.status ||
    (model.lifecycle_status === "running" ? "succeeded" : undefined);
  const deploymentStatusLabel = rawDeployStatus
    ? t(`workflow.${rawDeployStatus}`, { defaultValue: rawDeployStatus })
    : t("workflow.notDeployed");
  const deploymentStatusTone =
    rawDeployStatus === "succeeded"
      ? "success"
      : rawDeployStatus === "deploying" || rawDeployStatus === "pending"
        ? "warning"
        : rawDeployStatus === "failed"
          ? "danger"
          : "neutral";

  // 6. Registration Status
  const rawRegStatus =
    model.active_endpoint?.registration_status ||
    latestBuild?.registration_status ||
    (model.lifecycle_status === "registered" ||
    model.lifecycle_status === "running"
      ? "registered"
      : undefined);
  const registrationStatusLabel = rawRegStatus
    ? t(`workflow.${rawRegStatus}`, { defaultValue: rawRegStatus })
    : t("workflow.unregistered");
  const registrationStatusTone =
    rawRegStatus === "registered"
      ? "success"
      : rawRegStatus === "registering"
        ? "warning"
        : rawRegStatus === "failed"
          ? "danger"
          : "neutral";

  // 7. API Health
  const rawHealth = model.active_endpoint?.health_status;
  const healthStatusLabel = rawHealth
    ? t(`workflow.${rawHealth}`, { defaultValue: rawHealth })
    : t("workflow.notDeployed");
  const healthStatusTone =
    rawHealth === "healthy"
      ? "success"
      : rawHealth === "unhealthy"
        ? "danger"
        : "neutral";

  return (
    <section
      role="tabpanel"
      className="rounded-surface border border-border bg-surface p-6"
    >
      <div className="grid grid-cols-1 gap-x-12 gap-y-7 md:grid-cols-2">
        {/* Row 1: Model Name & Flavor */}
        <InfoItem
          label={t("workflow.name")}
          value={model.name}
        />
        <InfoItem
          label={t("workflow.flavor")}
          value={model.flavor || latestBuild?.flavor}
        />

        {/* Row 2: Access Mode & Version */}
        <InfoItem
          label={t("workflow.accessMode")}
          value={t(`workflow.${model.access_mode}`)}
        />
        <InfoItem
          label={t("workflow.version")}
          value=
          {versionNumber}
        />

        {/* Row 3: Build Status & Deployment Status */}
        <InfoItem
          label={t("workflow.buildStatus")}
          value={
            <Badge variant={buildStatusTone}>{buildStatusLabel}</Badge>
          }
        />
        <InfoItem
          label={t("workflow.deploymentStatus")}
          value={
            <Badge variant={deploymentStatusTone}>
              {deploymentStatusLabel}
            </Badge>
          }
        />

        {/* Row 4: Registration Status & Running Status */}
        <InfoItem
          label={t("workflow.registrationStatus")}
          value={
            <Badge variant={registrationStatusTone}>
              {registrationStatusLabel}
            </Badge>
          }
        />
        <InfoItem
          label={t("workflow.runningStatus")}
          value={
            <Badge variant={runningStatusTone}>{runningStatusLabel}</Badge>
          }
        />

        {/* Row 5: Model Status & API Health */}
        <InfoItem
          label={t("workflow.modelStatus")}
          value={
            <Badge variant={modelStatusTone}>
              {t(`workflow.${lifecycleStatus}`)}
            </Badge>
          }
        />
        <InfoItem
          label={t("workflow.health")}
          value={
            <Badge variant={healthStatusTone}>{healthStatusLabel}</Badge>
          }
        />

        {/* Row 6: Created at & Updated at */}
        <InfoItem
          label={t("workflow.createdAt")}
          value={
          <>
            {formatDateTime(model.created_at, i18n.language)}
          </>
          }
        />
        <InfoItem
          label={t("workflow.updatedAt")}
          value={
          <>
            {formatDateTime(model.updated_at, i18n.language)}
          </>
          }
        />
      </div>
    </section>
  );
}

export default InformationOverviewPage;
