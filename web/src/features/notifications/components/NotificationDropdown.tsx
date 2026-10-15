import { Button } from "@/shared/components/Button";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Bell, CheckCheck, Loader2 } from "lucide-react";
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  useDeleteNotification,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadNotificationCount,
} from "@/features/notifications/hooks/useNotifications";
import { NotificationItemComponent } from "@/features/notifications/components/NotificationItem";

export const NotificationDropdown: React.FC = () => {
  const { t } = useTranslation("notifications");
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const { data: countData } = useUnreadNotificationCount();
  const unreadCount = countData?.unread_count ?? 0;

  const { data: listData, isLoading } = useNotifications({
    page_size: 5,
  });

  const { mutate: markRead } = useMarkNotificationRead();
  const { mutate: markAllRead, isPending: isMarkingAll } = useMarkAllNotificationsRead();
  const { mutate: deleteItem } = useDeleteNotification();

  const notifications = listData?.results ?? [];

  return (
    <DropdownMenu.Root open={open} onOpenChange={setOpen}>
      <DropdownMenu.Trigger asChild>
        <Button
          size="icon"
          variant="secondary"
          className="relative"
          aria-label={t("title")}
          title={t("title")}
        >
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <span
              // typography-ignore: notification count micro-badge
              className="absolute -top-1 -right-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-color-danger-foreground shadow-xs animate-in zoom-in-50 duration-200"
            >
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </Button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 w-80 sm:w-96 rounded-overlay border border-border bg-surface p-0 shadow-lg outline-hidden animate-in fade-in-0 zoom-in-95 data-[side=bottom]:slide-in-from-top-2"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="text-style-body-strong font-semibold text-color-foreground">
                {t("title")}
              </span>
              {unreadCount > 0 && (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-style-caption-strong text-color-primary">
                  {unreadCount} {t("status.unreadCount")}
                </span>
              )}
            </div>

            {unreadCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 gap-1 text-color-primary hover:text-color-primary"
                disabled={isMarkingAll}
                onClick={() => markAllRead()}
              >
                <CheckCheck className="h-3.5 w-3.5" />
                <span>{t("actions.markAllAsRead")}</span>
              </Button>
            )}
          </div>

          {/* List Content */}
          <div className="max-h-[380px] overflow-y-auto p-2 flex flex-col gap-1.5 divide-y-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-8 text-color-foreground-muted gap-2 text-style-body">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>{t("status.loading")}</span>
              </div>
            ) : notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center px-4">
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-surface-muted text-color-foreground-muted">
                  <Bell className="h-5 w-5" />
                </div>
                <p className="text-style-body-strong text-color-foreground">
                  {t("status.emptyTitle")}
                </p>
                <p className="text-style-caption text-color-foreground-muted mt-0.5">
                  {t("status.emptyDescription")}
                </p>
              </div>
            ) : (
              notifications.map((item) => (
                <NotificationItemComponent
                  key={item.id}
                  notification={item}
                  isCompact
                  onMarkRead={(id) => markRead(id)}
                  onDelete={(id) => deleteItem(id)}
                  onCloseDropdown={() => setOpen(false)}
                />
              ))
            )}
          </div>

          {/* Footer View All Link */}
          <div className="border-t border-border p-2">
            <Button
              variant="secondary"
              fullWidth
              className="h-9 justify-center"
              onClick={() => {
                setOpen(false);
                navigate("/dashboard/notifications");
              }}
            >
              {t("actions.viewAll")}
            </Button>
          </div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
};
