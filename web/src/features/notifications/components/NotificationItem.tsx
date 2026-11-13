import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { cn } from "@/shared/lib/cn";
import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  Box,
  Check,
  Cpu,
  Rocket,
  Trash2,
} from "lucide-react";
import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { getNotificationDestination } from "@/features/notifications/lib/notificationRoutes";
import { formatTimeAgo } from "@/features/notifications/lib/timeAgo";
import type {
  NotificationItem as NotificationItemType,
  NotificationLevel,
  NotificationType,
} from "@/features/notifications/types";

interface NotificationItemProps {
  notification: NotificationItemType;
  onMarkRead?: (id: string) => void;
  onDelete?: (id: string) => void;
  isCompact?: boolean;
  onCloseDropdown?: () => void;
}

const TYPE_ICONS: Record<NotificationType, React.ReactNode> = {
  training: <Cpu className="h-5 w-5" />,
  build: <Box className="h-5 w-5" />,
  deployment: <Rocket className="h-5 w-5" />,
  drift: <Activity className="h-5 w-5" />,
  alert: <AlertTriangle className="h-5 w-5" />,
  system: <Bell className="h-5 w-5" />,
  project: <Bot className="h-5 w-5" />,
};

const LEVEL_VARIANTS: Record<
  NotificationLevel,
  "neutral" | "info" | "success" | "warning" | "danger"
> = {
  info: "info",
  success: "success",
  warning: "warning",
  error: "danger",
};

export const NotificationItemComponent: React.FC<NotificationItemProps> = ({
  notification,
  onMarkRead,
  onDelete,
  isCompact = false,
  onCloseDropdown,
}) => {
  const { t, i18n } = useTranslation("notifications");
  const navigate = useNavigate();
  const handleCardClick = (e: React.MouseEvent) => {
    // If user clicked action buttons, don't trigger link navigation
    if ((e.target as HTMLElement).closest("button")) {
      return;
    }

    if (!notification.is_read && onMarkRead) {
      onMarkRead(notification.id);
    }

    const destination = getNotificationDestination(notification);
    if (destination) {
      if (onCloseDropdown) {
        onCloseDropdown();
      }
      navigate(destination);
    }
  };

  const timeDisplay = formatTimeAgo(notification.created_at, i18n.language);

  return (
    <div
      onClick={handleCardClick}
      className={cn(
        "group relative flex cursor-pointer items-start gap-3 rounded-surface border border-border bg-surface text-color-foreground transition-all duration-150 hover:border-primary/40 hover:bg-surface-hover/60",
        isCompact ? "p-3" : "p-4",
      )}
    >
      {/* Type Icon Indicator */}
      <div
        className={cn(
          "flex shrink-0 items-center justify-center rounded-surface border",
          notification.level === "error" &&
            "border-danger-border bg-danger-subtle text-color-danger",
          notification.level === "warning" &&
            "border-warning-border bg-warning-subtle text-color-warning",
          notification.level === "success" &&
            "border-success-border bg-success-subtle text-color-success",
          notification.level === "info" &&
            "border-info-border bg-info-subtle text-color-info",
          isCompact ? "h-8 w-8" : "h-9 w-9",
        )}
      >
        {TYPE_ICONS[notification.type] || <Bell className="h-4 w-4" />}
      </div>

      {/* Content */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 overflow-hidden">
            <h4
              className={cn(
                "truncate font-semibold text-color-foreground",
                isCompact
                  ? "text-style-caption-strong"
                  : "text-style-body-strong",
              )}
            >
              {notification.title}
            </h4>

            {!notification.is_read && (
              <span
                className={cn(
                  "shrink-0 select-none text-color-danger font-bold",
                  isCompact
                    ? "text-style-caption-strong"
                    : "text-style-body-strong",
                )}
                title={t("status.unread")}
                aria-label={t("status.unread")}
              >
                *
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-style-caption text-color-foreground-muted whitespace-nowrap">
              {timeDisplay}
            </span>
          </div>
        </div>

        <p
          className={cn(
            "text-color-foreground-muted",
            isCompact ? "line-clamp-2 text-style-caption" : "text-style-body",
          )}
        >
          {notification.message}
        </p>

        {/* Action tags and links */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Badge
              variant={LEVEL_VARIANTS[notification.level]}
              className="capitalize py-0 px-2"
            >
              {t(`types.${notification.level}`, notification.level)}
            </Badge>
          </div>

          {/* Quick Item Actions */}
          <div className="flex items-center gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
            {onMarkRead && (
              <Button
                variant="secondary"
                size="icon"
                border={false}
                disabled={notification.is_read}
                title={
                  notification.is_read
                    ? t("actions.alreadyRead")
                    : t("actions.markAsRead")
                }
                aria-label={
                  notification.is_read
                    ? t("actions.alreadyRead")
                    : t("actions.markAsRead")
                }
                onClick={(e) => {
                  e.stopPropagation();
                  if (!notification.is_read) {
                    onMarkRead(notification.id);
                  }
                }}
              >
                <Check className="h-4 w-4" />
              </Button>
            )}

            {onDelete && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-color-foreground-muted hover:text-color-danger"
                title={t("actions.delete")}
                aria-label={t("actions.delete")}
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(notification.id);
                }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
