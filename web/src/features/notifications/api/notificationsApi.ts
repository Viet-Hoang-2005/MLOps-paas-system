import type {
  NotificationFilterParams,
  NotificationItem,
  NotificationListResponse,
  UnreadCountResponse,
} from "@/features/notifications/types";
import { apiClient } from "@/shared/api/client";
import { controlPlaneURL } from "@/shared/api/config";

export const listNotifications = async (
  params?: NotificationFilterParams,
): Promise<NotificationListResponse> => {
  const query = new URLSearchParams();
  if (params?.is_read !== undefined) {
    query.set("is_read", String(params.is_read));
  }
  if (params?.type) {
    query.set("type", params.type);
  }
  if (params?.search) {
    query.set("search", params.search);
  }
  if (params?.page) {
    query.set("page", String(params.page));
  }
  if (params?.page_size) {
    query.set("page_size", String(params.page_size));
  }

  const queryString = query.toString();
  const endpoint = queryString
    ? `/notifications/?${queryString}`
    : "/notifications/";

  const { data } = await apiClient.get<NotificationListResponse>(
    controlPlaneURL(endpoint),
  );
  return data;
};

export const getUnreadCount = async (): Promise<UnreadCountResponse> => {
  const { data } = await apiClient.get<UnreadCountResponse>(
    controlPlaneURL("/notifications/unread-count/"),
  );
  return data;
};

export const markNotificationAsRead = async (
  id: string,
): Promise<NotificationItem> => {
  const { data } = await apiClient.patch<NotificationItem>(
    controlPlaneURL(`/notifications/${id}/read/`),
  );
  return data;
};

export const markAllNotificationsAsRead = async (): Promise<{ updated: number }> => {
  const { data } = await apiClient.post<{ updated: number }>(
    controlPlaneURL("/notifications/mark-all-read/"),
  );
  return data;
};

export const deleteNotification = async (id: string): Promise<void> => {
  await apiClient.delete(controlPlaneURL(`/notifications/${id}/`));
};

