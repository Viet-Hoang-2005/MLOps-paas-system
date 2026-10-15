import { Button } from "@/shared/components/Button";
import { PageHeader } from "@/shared/components/PageHeader";
import { Search } from "@/shared/components/Search";
import { cn } from "@/shared/lib/cn";
import {
  Activity,
  AlertTriangle,
  Bell,
  Box,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Cpu,
  Inbox,
  Loader2,
  RefreshCw,
  Rocket,
} from "lucide-react";
import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { NotificationItemComponent } from "@/features/notifications/components/NotificationItem";
import {
  useDeleteNotification,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadNotificationCount,
} from "@/features/notifications/hooks/useNotifications";
import type { NotificationType } from "@/features/notifications/types";

type FilterTab = "all" | "unread" | NotificationType;

export default function NotificationsPage() {
  const { t } = useTranslation("notifications");
  const [activeTab, setActiveTab] = useState<FilterTab>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const filterParams = useMemo(() => {
    return {
      is_read: activeTab === "unread" ? false : undefined,
      type:
        activeTab !== "all" && activeTab !== "unread"
          ? (activeTab as NotificationType)
          : undefined,
      search: searchQuery.trim() || undefined,
      page,
      page_size: pageSize,
    };
  }, [activeTab, searchQuery, page]);

  const {
    data: listData,
    isLoading,
    isFetching,
    refetch,
  } = useNotifications(filterParams);

  const { data: countData } = useUnreadNotificationCount();
  const unreadCount = countData?.unread_count ?? 0;

  const { mutate: markRead } = useMarkNotificationRead();
  const { mutate: markAllRead, isPending: isMarkingAll } = useMarkAllNotificationsRead();
  const { mutate: deleteItem } = useDeleteNotification();

  const notifications = listData?.results ?? [];
  const totalCount = listData?.count ?? 0;
  const totalPages = Math.ceil(totalCount / pageSize);

  const handleTabChange = (tab: FilterTab) => {
    setActiveTab(tab);
    setPage(1);
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
    setPage(1);
  };

  const filterTabs: Array<{ id: FilterTab; label: string; icon: React.ReactNode }> = [
    { id: "all", label: t("filters.all"), icon: <Inbox className="h-4 w-4" /> },
    { id: "unread", label: t("filters.unread"), icon: <Bell className="h-4 w-4" /> },
    { id: "training", label: t("filters.training"), icon: <Cpu className="h-4 w-4" /> },
    { id: "build", label: t("filters.build"), icon: <Box className="h-4 w-4" /> },
    { id: "deployment", label: t("filters.deployment"), icon: <Rocket className="h-4 w-4" /> },
    { id: "drift", label: t("filters.drift"), icon: <Activity className="h-4 w-4" /> },
    { id: "alert", label: t("filters.alert"), icon: <AlertTriangle className="h-4 w-4" /> },
  ];

  return (
    <section className="flex flex-1 flex-col gap-6">
      <PageHeader
        title={t("title")}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              className="gap-1.5"
              disabled={isFetching}
              onClick={() => refetch()}
            >
              <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
              <span>{t("actions.refresh")}</span>
            </Button>

            {unreadCount > 0 && (
              <Button
                variant="primary"
                size="sm"
                className="gap-1.5"
                disabled={isMarkingAll}
                onClick={() => markAllRead()}
              >
                <CheckCheck className="h-4 w-4" />
                <span>{t("actions.markAllAsRead")}</span>
              </Button>
            )}
          </div>
        }
      />

      {/* Filter and Search Bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-4">
        {/* Horizontal filter tabs */}
        <div className="flex items-center gap-1 overflow-x-auto no-scrollbar py-0.5">
          {filterTabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => handleTabChange(tab.id)}
                className={cn(
                  "flex items-center gap-1.5 rounded-control px-3 py-1.5 text-style-caption-strong transition-all whitespace-nowrap",
                  isActive
                    ? "bg-primary text-color-primary-foreground shadow-xs"
                    : "text-color-foreground-muted hover:bg-surface-hover hover:text-color-foreground",
                )}
              >
                {tab.icon}
                <span>{tab.label}</span>
                {tab.id === "unread" && unreadCount > 0 && (
                  <span
                    className={cn(
                      // typography-ignore: notification count micro-badge
                      "ml-1 flex h-4 min-w-[16px] items-center justify-center rounded-full px-1 text-[10px] font-bold",
                      isActive ? "bg-surface text-color-primary" : "bg-danger text-color-danger-foreground",
                    )}
                  >
                    {unreadCount}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Search Box */}
        <div className="w-full sm:w-72 shrink-0">
          <Search
            placeholder={t("searchPlaceholder")}
            value={searchQuery}
            onChange={handleSearchChange}
            onClear={() => {
              setSearchQuery("");
              setPage(1);
            }}
          />
        </div>
      </div>

      {/* Notifications List */}
      <div className="flex flex-col gap-3">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 text-color-foreground-muted gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-color-primary" />
            <p className="text-style-body">{t("status.loading")}</p>
          </div>
        ) : notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center rounded-surface border border-dashed border-border bg-surface-muted/30 p-8">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-surface-muted text-color-foreground-muted">
              <Bell className="h-6 w-6" />
            </div>
            <h3 className="text-style-body-strong font-semibold text-color-foreground">
              {searchQuery || activeTab !== "all"
                ? t("status.emptyFiltered")
                : t("status.emptyTitle")}
            </h3>
            <p className="text-style-body text-color-foreground-muted max-w-sm mt-1">
              {t("status.emptyDescription")}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {notifications.map((item) => (
              <NotificationItemComponent
                key={item.id}
                notification={item}
                onMarkRead={(id) => markRead(id)}
                onDelete={(id) => deleteItem(id)}
              />
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-border pt-4 mt-2">
            <p className="text-style-caption text-color-foreground-muted">
              {t("pagination.showing", { count: totalCount })}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                className="gap-1"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="h-4 w-4" />
                <span>{t("pagination.prev")}</span>
              </Button>
              <span className="text-style-caption px-2 font-medium">
                {page} / {totalPages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                className="gap-1"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                <span>{t("pagination.next")}</span>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
