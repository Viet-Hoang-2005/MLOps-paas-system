import type { NotificationFilterParams } from "./types";

export const notificationQueryKeys = {
  all: ["notifications"] as const,
  lists: () => [...notificationQueryKeys.all, "list"] as const,
  list: (filters?: NotificationFilterParams) =>
    [...notificationQueryKeys.lists(), filters ?? {}] as const,
  unreadCount: () => [...notificationQueryKeys.all, "unread-count"] as const,
};

