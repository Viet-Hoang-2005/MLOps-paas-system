import type { Build } from "@/features/projects/types";

export function canRebuild(build: Build): boolean {
  return (
    build.deletion_state === "active" &&
    build.registration_status !== "registering" &&
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
