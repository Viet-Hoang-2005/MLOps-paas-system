import type { NotificationItem } from "@/features/notifications/types";

/**
 * Resolves the destination URL for a given notification item based on its type.
 *
 * Rules:
 * - Model project: /dashboard/projects
 * - Training: /dashboard/projects/<projectId>/training
 * - Packaging (build) & Deployment: /dashboard/projects/<projectId>/deployment
 * - Data drift: /dashboard/projects/<projectId>/monitoring
 * - Alert: /dashboard/projects/<projectId>/overview
 */
export function getNotificationDestination(notification: NotificationItem): string {
  const metadataProjectId =
    typeof notification.metadata?.project_id === "string"
      ? notification.metadata.project_id
      : undefined;

  const linkProjectId = notification.link
    ? notification.link.match(/\/projects\/([a-zA-Z0-9_-]+)/)?.[1]
    : undefined;

  const projectId = metadataProjectId || linkProjectId;

  switch (notification.type) {
    case "project":
      return "/dashboard/projects";

    case "training":
      return projectId
        ? `/dashboard/projects/${projectId}/training`
        : "/dashboard/training";

    case "build":
    case "deployment":
      return projectId
        ? `/dashboard/projects/${projectId}/deployment`
        : "/dashboard/deployment";

    case "drift":
      return projectId
        ? `/dashboard/projects/${projectId}/monitoring`
        : "/dashboard/monitoring";

    case "alert":
      return projectId
        ? `/dashboard/projects/${projectId}/overview`
        : "/dashboard/overview";

    default:
      if (notification.link) {
        const sanitized = notification.link.replace(/\/deployments\b/g, "/deployment");
        return sanitized.startsWith("/dashboard")
          ? sanitized
          : `/dashboard${sanitized.startsWith("/") ? "" : "/"}${sanitized}`;
      }
      return "/dashboard/projects";
  }
}

