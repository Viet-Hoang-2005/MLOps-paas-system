import { Button } from "@/shared/components/Button";
import { PageHeader } from "@/shared/components/PageHeader";
import { Search } from "@/shared/components/Search";
import { Select, type SelectOption } from "@/shared/components/Select";
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

  const filterOptions = useMemo<SelectOption[]>(() => [
    {
      value: "all",
      label: (
        <span className="flex items-center gap-2">
          <Inbox className="h-4 w-4 text-color-foreground-muted" />
          <span>{t("filters.all")}</span>
        </span>
      ),
    },
    {
      value: "unread",
      label: (
        <span className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-color-foreground-muted" />
          <span>{t("filters.unread")}</span>
        </span>
      ),
      badge: unreadCount > 0 ? (
        <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-style-caption-strong text-color-danger-foreground">
          {unreadCount}
        </span>
      ) : undefined,
    },
    {
      value: "training",
      label: (
        <span className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-color-foreground-muted" />
          <span>{t("filters.training")}</span>
        </span>
      ),
    },
    {
      value: "build",
      label: (
        <span className="flex items-center gap-2">
          <Box className="h-4 w-4 text-color-foreground-muted" />
          <span>{t("filters.build")}</span>
        </span>
      ),
    },
    {
      value: "deployment",
      label: (
        <span className="flex items-center gap-2">
          <Rocket className="h-4 w-4 text-color-foreground-muted" />
          <span>{t("filters.deployment")}</span>
        </span>
      ),
    },
    {
      value: "drift",
      label: (
        <span className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-color-foreground-muted" />
          <span>{t("filters.drift")}</span>
        </span>
      ),
    },
    {
      value: "alert",
      label: (
        <span className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-color-foreground-muted" />
          <span>{t("filters.alert")}</span>
        </span>
      ),
    },
  ], [t, unreadCount]);

  return (
    <section className="flex flex-1 flex-col gap-6">
      <PageHeader
        title={t("title")}
        actions={
          unreadCount > 0 ? (
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
          ) : undefined
        }
      />

      {/* Search, Refresh and Type Filter Bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-4">
        {/* Left: Search component + Refresh button */}
        <div className="flex flex-1 items-center gap-2">
          <div className="w-full sm:w-72">
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

          <Button
            variant="secondary"
            size="md"
            className="shrink-0 gap-1.5"
            disabled={isFetching}
            onClick={() => refetch()}
            title={t("actions.refresh")}
          >
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
            <span>{t("actions.refresh")}</span>
          </Button>
        </div>

        {/* Right: Select component to filter notification types */}
        <div className="w-full sm:w-60 shrink-0">
          <Select
            className="h-10 text-style-body"
            value={activeTab}
            onChange={(val) => handleTabChange(val as FilterTab)}
            options={filterOptions}
            placeholder={t("filters.all")}
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
