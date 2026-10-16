import type { NotificationItem } from "@/features/notifications/types";

export function createMockNotification(
  overrides: Partial<NotificationItem> = {},
): NotificationItem {
  return {
    id: "notif-1",
    type: "training",
    level: "success",
    title: "Training Job Completed",
    message: "Training job churn-model-1 completed with accuracy 0.95",
    link: "/dashboard/projects/project-1/training",
    metadata: { job_id: "job-1", accuracy: 0.95 },
    is_read: false,
    read_at: null,
    created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    ...overrides,
  };
}
