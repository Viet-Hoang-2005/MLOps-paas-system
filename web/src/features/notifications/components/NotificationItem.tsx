import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { cn } from "@/shared/lib/cn";
import {
  Activity,
  AlertTriangle,
  Bell,
  Box,
  Check,
  Cpu,
  ExternalLink,
  Rocket,
  Trash2,
} from "lucide-react";
import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
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
  training: <Cpu className="h-4 w-4" />,
  build: <Box className="h-4 w-4" />,
  deployment: <Rocket className="h-4 w-4" />,
  drift: <Activity className="h-4 w-4" />,
  alert: <AlertTriangle className="h-4 w-4" />,
  system: <Bell className="h-4 w-4" />,
};

const LEVEL_VARIANTS: Record<NotificationLevel, "neutral" | "info" | "success" | "warning" | "danger"> = {
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

    if (notification.link) {
      if (onCloseDropdown) {
        onCloseDropdown();
      }
      navigate(notification.link);
    }
  };

  const timeDisplay = formatTimeAgo(notification.created_at, i18n.language);

  return (
    <div
      onClick={handleCardClick}
      className={cn(
        "group relative flex items-start gap-3 rounded-surface border transition-all duration-150",
        notification.link ? "cursor-pointer hover:border-primary/40 hover:bg-surface-hover/70" : "",
        notification.is_read
          ? "border-border/60 bg-surface text-color-foreground"
          : "border-primary/20 bg-primary/5 text-color-foreground shadow-xs",
        isCompact ? "p-3" : "p-4",
      )}
    >
      {/* Type Icon Indicator */}
      <div
        className={cn(
          "flex shrink-0 items-center justify-center rounded-control border",
          notification.level === "error" && "border-danger-border bg-danger-subtle text-color-danger",
          notification.level === "warning" && "border-warning-border bg-warning-subtle text-color-warning",
          notification.level === "success" && "border-success-border bg-success-subtle text-color-success",
          notification.level === "info" && "border-info-border bg-info-subtle text-color-info",
          isCompact ? "h-8 w-8" : "h-9 w-9",
        )}
      >
        {TYPE_ICONS[notification.type] || <Bell className="h-4 w-4" />}
      </div>

      {/* Content */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 overflow-hidden">
            {!notification.is_read && (
              <span className="h-2 w-2 shrink-0 rounded-full bg-primary" title={t("status.unread")} />
            )}
            <h4
              className={cn(
                "truncate font-medium",
                isCompact ? "text-style-caption-strong" : "text-style-body-strong",
                !notification.is_read && "font-semibold text-color-primary",
              )}
            >
              {notification.title}
            </h4>
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
        <div className="mt-1 flex items-center justify-between gap-2 pt-1">
          <div className="flex items-center gap-2">
            <Badge variant={LEVEL_VARIANTS[notification.level]} className="capitalize py-0 px-2">
              {t(`types.${notification.type}`, notification.type)}
            </Badge>

            {notification.link && (
              <span className="flex items-center gap-1 text-style-caption text-color-primary font-medium hover:underline">
                {t("actions.viewDetails")}
                <ExternalLink className="h-3 w-3" />
              </span>
            )}
          </div>

          {/* Quick Item Actions */}
          <div className="flex items-center gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
            {!notification.is_read && onMarkRead && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-color-foreground-muted hover:text-color-primary"
                title={t("actions.markAsRead")}
                aria-label={t("actions.markAsRead")}
                onClick={(e) => {
                  e.stopPropagation();
                  onMarkRead(notification.id);
                }}
              >
                <Check className="h-3.5 w-3.5" />
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
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
