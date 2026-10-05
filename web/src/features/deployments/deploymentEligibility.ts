import type { Build, Deployment } from "@/features/projects/types";

export function isRegisteredBuild(build?: Build): boolean {
  return Boolean(
    build?.version_id && build.registration_status === "registered",
  );
}

export function projectDeploymentBlocked(
  attempts: Deployment[],
  builds: Build[],
  selected?: Deployment,
): boolean {
  const buildIds = new Set(builds.map((build) => build.id));
  const blocking = new Set(["pending", "deploying", "unconfirmed"]);
  return (
    Boolean(selected && blocking.has(selected.status)) ||
    attempts.some(
      (attempt) =>
        buildIds.has(attempt.build_id) && blocking.has(attempt.status),
    )
  );
}

export function isDeployableBuild(build?: Build, projectId?: string): boolean {
  return Boolean(
    build &&
    build.project_id === projectId &&
    build.status === "ready" &&
    build.deletion_state === "active" &&
    isRegisteredBuild(build),
  );
}

export function deploymentMatchesBuild(
  deployment: Deployment,
  build: Build,
): boolean {
  return (
    deployment.build_id === build.id &&
    deployment.version_id === build.version_id
  );
}
