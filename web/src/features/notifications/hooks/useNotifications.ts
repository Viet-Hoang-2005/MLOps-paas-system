import {
  deleteNotification,
  getUnreadCount,
  listNotifications,
  markAllNotificationsAsRead,
  markNotificationAsRead,
} from "@/features/notifications/api/notificationsApi";
import { notificationQueryKeys } from "@/features/notifications/queryKeys";
import type {
  NotificationFilterParams,
  NotificationListResponse,
  UnreadCountResponse,
} from "@/features/notifications/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export function useNotifications(filters?: NotificationFilterParams) {
  return useQuery<NotificationListResponse>({
    queryKey: notificationQueryKeys.list(filters),
    queryFn: () => listNotifications(filters),
  });
}

export function useUnreadNotificationCount() {
  return useQuery<UnreadCountResponse>({
    queryKey: notificationQueryKeys.unreadCount(),
    queryFn: getUnreadCount,
    refetchInterval: 15000, // Poll unread count every 15s
    refetchIntervalInBackground: false,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => markNotificationAsRead(id),
    onSuccess: () => {
      // Invalidate list and count queries
      queryClient.invalidateQueries({ queryKey: notificationQueryKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: notificationQueryKeys.unreadCount(),
      });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: markAllNotificationsAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationQueryKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: notificationQueryKeys.unreadCount(),
      });
    },
  });
}

export function useDeleteNotification() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteNotification(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationQueryKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: notificationQueryKeys.unreadCount(),
      });
    },
  });
}
