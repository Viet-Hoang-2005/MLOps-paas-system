import type { Build } from "@/features/projects/types";

export function isBuildImageMissing(build?: Build): boolean {
  return build?.status === "ready" && !build.image_uri;
}

export function canRebuild(build: Build): boolean {
  return (
    build.deletion_state === "active" &&
    (build.registration_status !== "registering" || isBuildImageMissing(build)) &&
    ["ready", "failed", "cancelled"].includes(build.status)
  );
}

export function canDeleteBuild(build: Build): boolean {
  return (
    build.deletion_state !== "deleting" &&
    !build.version_id &&
    !["registering", "registered"].includes(build.registration_status)
  );
}
