import { useState } from "react";
import {
  Bell,
  Bot,
  BrainCircuit,
  ChevronDown,
  GitBranch,
  Home,
  LineChart,
  LogOut,
  Menu,
  Settings,
  KeyRound,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink, useLocation } from "react-router-dom";
import { routes } from "@/app/router/paths";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { cn } from "@/shared/lib/cn";

interface DashboardSidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onToggle: () => void;
  onCloseMobile: () => void;
}

const sectionItems = [
  { key: "home", section: "overview", icon: Home },
  { key: "deployment", section: "deployment", icon: Bot },
  {
    key: "driftMonitoring",
    section: "monitoring",
    icon: LineChart,
  },
  {
    key: "modelTraining",
    section: "training",
    icon: BrainCircuit,
  },
  {
    key: "modelEvolution",
    section: "evolution",
    icon: GitBranch,
  },
] as const;

const utilityItems = [
  {
    key: "notification",
    to: routes.notifications,
    icon: Bell,
    match: routes.notifications,
  },
  {
    key: "setting",
    to: routes.profile,
    icon: Settings,
    match: "/dashboard/settings",
  },
  {
    key: "apiTokens",
    to: routes.apiTokens,
    icon: KeyRound,
    match: routes.apiTokens,
  },
] as const;

export default function Sidebar({
  collapsed,
  mobileOpen,
  onToggle,
  onCloseMobile,
}: DashboardSidebarProps) {
  const location = useLocation();
  const { logout } = useAuth();
  const { t } = useTranslation("common");
  const { selectedModel } = useModelSelection();
  const [modelGroupOpen, setModelGroupOpen] = useState(true);
  const [systemGroupOpen, setSystemGroupOpen] = useState(true);

  const managementItem = {
    key: "management",
    to: routes.projects,
    icon: Bot,
    match: routes.projects,
  };

  const modelItems = sectionItems.map((item) => ({
    ...item,
    to: selectedModel
      ? `/dashboard/projects/${selectedModel.id}/${item.section}`
      : `/dashboard/${item.section}`,
  }));

  const systemItems = utilityItems;

  const isItemActive = (key: string, section?: string, to?: string) => {
    if (key === "management") {
      return (
        location.pathname === routes.projects ||
        location.pathname === routes.newProject
      );
    }
    if (section) {
      const regex = new RegExp(
        `^/dashboard/(?:projects/[^/]+/)?${section}(?:/|$)`,
      );
      return regex.test(location.pathname);
    }
    if (to) {
      return location.pathname === to || location.pathname.startsWith(to);
    }
    return false;
  };

  const itemClass = (active: boolean) =>
    cn(
      "group flex h-10 items-center gap-3 rounded-compact px-3 text-style-body-strong transition-colors focus-visible:ring-2 focus-visible:ring-ring",
      active
        ? "bg-primary text-color-primary-foreground"
        : "text-color-muted-foreground hover:bg-muted hover:text-color-foreground",
      "md:justify-center md:px-0 xl:justify-start xl:px-3",
      collapsed && "xl:justify-center xl:px-0",
    );

  const labelClass = cn(
    "truncate md:hidden xl:block",
    collapsed && "xl:hidden",
  );

  const renderItem = (
    item:
      | typeof managementItem
      | (typeof modelItems)[number]
      | (typeof utilityItems)[number],
  ) => {
    const Icon = item.icon;
    const active =
      "section" in item
        ? isItemActive(item.key, item.section)
        : isItemActive(item.key, undefined, item.match);
    return (
      <NavLink
        key={item.key}
        to={item.to}
        onClick={onCloseMobile}
        className={itemClass(active)}
        title={collapsed ? t(`navigation.${item.key}`) : undefined}
      >
        <Icon className="h-5 w-5 shrink-0" />
        <span className={labelClass}>{t(`navigation.${item.key}`)}</span>
      </NavLink>
    );
  };

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-overlay md:hidden"
          onClick={onCloseMobile}
          aria-label={t("actions.closeNavigation")}
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-56 flex-col border-r border-border bg-surface transition-[transform,width] duration-200 md:static md:z-20 md:w-17 md:translate-x-0 xl:w-56",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          collapsed && "xl:w-17",
        )}
      >
        <div className="flex h-16 items-center justify-between border-b border-border px-3 md:hidden">
          <span className="text-style-body text-color-muted-foreground">
            {t("navigation.managementGroup")}
          </span>
          <button
            type="button"
            onClick={onCloseMobile}
            className="flex h-10 w-10 items-center justify-center rounded-surface text-color-muted-foreground hover:bg-muted hover:text-color-foreground"
            aria-label={t("actions.closeNavigation")}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="hidden h-12 items-center border-b border-border px-3 md:flex md:justify-center xl:justify-between">
          <span
            className={cn(
              "text-style-body text-color-muted-foreground md:hidden xl:block",
              collapsed && "xl:hidden",
            )}
          >
            {t("navigation.managementGroup")}
          </span>
          <button
            type="button"
            onClick={onToggle}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-surface text-color-muted-foreground hover:bg-muted hover:text-color-foreground"
            aria-label={
              collapsed
                ? t("actions.expandSidebar")
                : t("actions.collapseSidebar")
            }
          >
            <Menu className="h-5 w-5" />
          </button>
        </div>

        <nav
          className="flex min-h-0 flex-1 flex-col overflow-y-auto p-3"
          aria-label={t("navigation.primary")}
        >
          <div className="space-y-1">{renderItem(managementItem)}</div>

          <div
            className={cn(
              "-mx-3 flex items-center justify-between border-b border-border transition-all",
              collapsed
                ? "h-10 px-3 md:h-0 md:my-2 md:px-0 xl:h-0 xl:my-2 xl:px-0"
                : "h-10 px-3 mt-3 mb-2 cursor-pointer select-none group/model md:h-0 md:my-2 md:px-0 xl:h-10 xl:px-3 xl:mt-3 xl:mb-2",
            )}
            onClick={() => !collapsed && setModelGroupOpen((open) => !open)}
          >
            <span
              className={cn(
                "text-style-body text-color-muted-foreground group-hover/model:text-color-foreground transition-colors md:hidden xl:block",
                collapsed && "xl:hidden",
              )}
            >
              {t("navigation.modelGroup")}
            </span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setModelGroupOpen((open) => !open);
              }}
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-compact text-color-muted-foreground hover:bg-muted hover:text-color-foreground transition-colors md:hidden xl:flex",
                collapsed && "xl:hidden",
              )}
              aria-label={
                modelGroupOpen
                  ? t("actions.collapseGroup")
                  : t("actions.expandGroup")
              }
            >
              <ChevronDown
                className={cn(
                  "h-4 w-4 transition-transform duration-200",
                  !modelGroupOpen && "-rotate-90",
                )}
              />
            </button>
          </div>

          {(modelGroupOpen || collapsed) && (
            <div className="space-y-1">{modelItems.map(renderItem)}</div>
          )}

          <div
            className={cn(
              "-mx-3 flex items-center justify-between border-b border-border transition-all",
              collapsed
                ? "h-10 px-3 md:h-0 md:my-2 md:px-0 xl:h-0 xl:my-2 xl:px-0"
                : "h-10 px-3 mt-3 mb-2 cursor-pointer select-none group/system md:h-0 md:my-2 md:px-0 xl:h-10 xl:px-3 xl:mt-3 xl:mb-2",
            )}
            onClick={() => !collapsed && setSystemGroupOpen((open) => !open)}
          >
            <span
              className={cn(
                "text-style-body text-color-muted-foreground group-hover/system:text-color-foreground transition-colors md:hidden xl:block",
                collapsed && "xl:hidden",
              )}
            >
              {t("navigation.systemGroup")}
            </span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setSystemGroupOpen((open) => !open);
              }}
              className={cn(
                "flex h-7 w-7 items-center justify-center rounded-compact text-color-muted-foreground hover:bg-muted hover:text-color-foreground transition-colors md:hidden xl:flex",
                collapsed && "xl:hidden",
              )}
              aria-label={
                systemGroupOpen
                  ? t("actions.collapseGroup")
                  : t("actions.expandGroup")
              }
            >
              <ChevronDown
                className={cn(
                  "h-4 w-4 transition-transform duration-200",
                  !systemGroupOpen && "-rotate-90",
                )}
              />
            </button>
          </div>

          {(systemGroupOpen || collapsed) && (
            <div className="space-y-1">{systemItems.map(renderItem)}</div>
          )}

          <div className="mt-auto pt-3 border-t border-border">
            <button
              type="button"
              onClick={logout}
              className={cn(
                "flex h-10 w-full items-center gap-3 rounded-surface px-3 text-style-body-strong text-color-muted-foreground transition-colors hover:bg-danger-subtle hover:text-color-danger md:justify-center md:px-0 xl:justify-start xl:px-3",
                collapsed && "xl:justify-center xl:px-0",
              )}
              title={collapsed ? t("actions.logout") : undefined}
            >
              <LogOut className="h-5 w-5 shrink-0" />
              <span className={labelClass}>{t("actions.logout")}</span>
            </button>
          </div>
        </nav>
      </aside>
    </>
  );
}
