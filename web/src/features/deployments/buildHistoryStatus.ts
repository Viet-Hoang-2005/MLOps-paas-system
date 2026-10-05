import type { Build, Deployment } from "@/features/projects/types";

type StatusPresentation = {
  label: string;
  tone: "neutral" | "info" | "success" | "warning" | "danger";
};

export const buildStatuses = {
  pending: { label: "workflow.pending", tone: "info" },
  queued: { label: "workflow.queued", tone: "info" },
  building: { label: "workflow.building", tone: "info" },
  ready: { label: "workflow.buildSucceeded", tone: "success" },
  failed: { label: "workflow.buildFailed", tone: "danger" },
  cancelled: { label: "workflow.cancelled", tone: "warning" },
} as const satisfies Record<Build["status"], StatusPresentation>;

export const registrationStatuses = {
  unregistered: { label: "workflow.unregistered", tone: "neutral" },
  registering: { label: "workflow.registering", tone: "info" },
  registered: { label: "workflow.registered", tone: "success" },
  failed: { label: "workflow.registrationFailed", tone: "danger" },
} as const satisfies Record<Build["registration_status"], StatusPresentation>;

export const deploymentStatuses = {
  not_deployed: { label: "workflow.notDeployed", tone: "neutral" },
  pending: { label: "workflow.pending", tone: "info" },
  deploying: { label: "workflow.deploying", tone: "info" },
  healthy: { label: "workflow.deployHealthy", tone: "success" },
  unhealthy: { label: "workflow.deployUnhealthy", tone: "danger" },
  failed: { label: "workflow.deployFailed", tone: "danger" },
  stopped: { label: "workflow.deployStopped", tone: "neutral" },
  unconfirmed: { label: "workflow.deployUnconfirmed", tone: "warning" },
} as const satisfies Record<
  Deployment["status"] | "not_deployed",
  StatusPresentation
>;

export function getBuildDeploymentStatus(
  buildId: string,
  deployments: Deployment[],
) {
  // The API orders deployment attempts newest first. Use the latest attempt's
  // actual status; a historical deployed_at timestamp does not imply health.
  return (
    deployments.find((deployment) => deployment.build_id === buildId)?.status ??
    "not_deployed"
  );
}

export function matchesBuildStatus(build: Build, status: string) {
  return status === "all" || build.status === status;
}
