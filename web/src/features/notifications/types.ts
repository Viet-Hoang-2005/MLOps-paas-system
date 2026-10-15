export type NotificationType =
  | "training"
  | "build"
  | "deployment"
  | "drift"
  | "alert"
  | "system";

export type NotificationLevel = "info" | "success" | "warning" | "error";

export interface NotificationItem {
  id: string; // public_id
  type: NotificationType;
  level: NotificationLevel;
  title: string;
  message: string;
  link?: string;
  metadata?: Record<string, unknown>;
  is_read: boolean;
  created_at: string;
  read_at?: string | null;
}

export interface NotificationListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: NotificationItem[];
}

export interface UnreadCountResponse {
  unread_count: number;
}

export interface NotificationFilterParams {
  is_read?: boolean;
  type?: NotificationType;
  search?: string;
  page?: number;
  page_size?: number;
}
