import { routes } from "@/app/router/paths";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { cn } from "@/shared/lib/cn";
import {
  Bell,
  Bot,
  Box,
  BrainCircuit,
  ChevronDown,
  GitBranch,
  Home,
  KeyRound,
  LineChart,
  LogOut,
  Menu,
  Settings,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useLocation } from "react-router-dom";

interface DashboardSidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onToggle: () => void;
  onCloseMobile: () => void;
}

const sectionItems = [
  { key: "home", section: "overview", icon: Home },
  { key: "deployment", section: "deployment", icon: Box },
  { key: "driftMonitoring", section: "monitoring", icon: LineChart },
  { key: "modelTraining", section: "training", icon: BrainCircuit },
  { key: "modelEvolution", section: "evolution", icon: GitBranch },
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
  const [narrowExpanded, setNarrowExpanded] = useState(false);
  const [prevPathname, setPrevPathname] = useState(location.pathname);

  if (prevPathname !== location.pathname) {
    setPrevPathname(location.pathname);
    setNarrowExpanded(false);
  }

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 1280) {
        setNarrowExpanded(false);
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const handleToggle = () => {
    if (typeof window !== "undefined" && window.innerWidth < 1280) {
      setNarrowExpanded((prev) => !prev);
    } else {
      onToggle();
    }
  };

  const handleCloseAll = () => {
    onCloseMobile();
    setNarrowExpanded(false);
  };

  const managementItem = {
    key: "management",
    to: routes.projects,
    icon: Bot,
    match: routes.projects,
    iconClassName: "-translate-y-0.5",
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
      narrowExpanded ? "md:justify-start md:px-3" : "md:justify-center md:px-0",
      collapsed ? "xl:justify-center xl:px-0" : "xl:justify-start xl:px-3",
    );

  const labelClass = cn(
    "truncate",
    narrowExpanded ? "md:block" : "md:hidden",
    collapsed ? "xl:hidden" : "xl:block",
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
    const iconClassName =
      "iconClassName" in item ? item.iconClassName : undefined;
    return (
      <NavLink
        key={item.key}
        to={item.to}
        onClick={handleCloseAll}
        className={itemClass(active)}
        title={!narrowExpanded || collapsed ? t(`navigation.${item.key}`) : undefined}
      >
        <Icon className={cn("h-5 w-5 shrink-0", iconClassName)} />
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

      {narrowExpanded && (
        <button
          type="button"
          className="fixed inset-0 top-16 z-20 hidden bg-overlay md:block xl:hidden animate-fade-in"
          onClick={() => setNarrowExpanded(false)}
          aria-label={t("actions.closeNavigation")}
        />
      )}

      {/* Permanent placeholder in flex layout for md (tablet/narrow) to eliminate layout shift */}
      <div
        className="hidden md:block md:w-17 md:shrink-0 xl:hidden"
        aria-hidden="true"
      />

      <aside
        className={cn(
          "flex flex-col border-r border-border bg-surface transition-[transform,width,box-shadow] duration-200",
          // Mobile (< md)
          "fixed inset-y-0 left-0 z-40 w-56",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          // Narrow desktop / tablet (md to xl): permanently fixed below header, width transitions over constant placeholder
          "md:fixed md:top-16 md:bottom-0 md:left-0 md:translate-x-0",
          narrowExpanded
            ? "md:z-30 md:w-56 md:shadow-(--shadow-overlay)"
            : "md:z-20 md:w-17 md:shadow-none",
          // Wide desktop (xl)
          "xl:static xl:top-auto xl:bottom-auto xl:left-auto xl:z-20 xl:translate-x-0 xl:shadow-none",
          collapsed ? "xl:w-17" : "xl:w-56",
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

        <div
          className={cn(
            "hidden h-12 items-center border-b border-border px-3 md:flex",
            narrowExpanded ? "md:justify-between" : "md:justify-center",
            collapsed ? "xl:justify-center" : "xl:justify-between",
          )}
        >
          <span
            className={cn(
              "truncate text-style-body text-color-muted-foreground",
              !narrowExpanded && "md:hidden",
              collapsed ? "xl:hidden" : "xl:block",
            )}
          >
            {t("navigation.managementGroup")}
          </span>
          <button
            type="button"
            onClick={handleToggle}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-surface text-color-muted-foreground hover:bg-muted hover:text-color-foreground"
            aria-label={
              narrowExpanded || (!collapsed && typeof window !== "undefined" && window.innerWidth >= 1280)
                ? t("actions.collapseSidebar")
                : t("actions.expandSidebar")
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
              narrowExpanded
                ? "md:h-10 md:px-3 md:mt-3 md:mb-2 md:cursor-pointer md:select-none"
                : "md:h-0 md:my-2 md:px-0",
              collapsed
                ? "xl:h-0 xl:my-2 xl:px-0"
                : "xl:h-10 xl:px-3 xl:mt-3 xl:mb-2 xl:cursor-pointer xl:select-none",
            )}
            onClick={() => {
              if (narrowExpanded || !collapsed) {
                setModelGroupOpen((open) => !open);
              }
            }}
          >
            <span
              className={cn(
                "text-style-body text-color-muted-foreground group-hover/model:text-color-foreground transition-colors",
                narrowExpanded ? "md:block" : "md:hidden",
                collapsed ? "xl:hidden" : "xl:block",
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
                "h-7 w-7 items-center justify-center rounded-compact text-color-muted-foreground hover:bg-muted hover:text-color-foreground transition-colors",
                narrowExpanded ? "md:flex" : "md:hidden",
                collapsed ? "xl:hidden" : "xl:flex",
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

          {((narrowExpanded ? modelGroupOpen : true) &&
            (collapsed ? true : modelGroupOpen)) && (
            <div className="space-y-1">{modelItems.map(renderItem)}</div>
          )}

          <div
            className={cn(
              "-mx-3 flex items-center justify-between border-b border-border transition-all",
              narrowExpanded
                ? "md:h-10 md:px-3 md:mt-3 md:mb-2 md:cursor-pointer md:select-none"
                : "md:h-0 md:my-2 md:px-0",
              collapsed
                ? "xl:h-0 xl:my-2 xl:px-0"
                : "xl:h-10 xl:px-3 xl:mt-3 xl:mb-2 xl:cursor-pointer xl:select-none",
            )}
            onClick={() => {
              if (narrowExpanded || !collapsed) {
                setSystemGroupOpen((open) => !open);
              }
            }}
          >
            <span
              className={cn(
                "text-style-body text-color-muted-foreground group-hover/system:text-color-foreground transition-colors",
                narrowExpanded ? "md:block" : "md:hidden",
                collapsed ? "xl:hidden" : "xl:block",
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
                "h-7 w-7 items-center justify-center rounded-compact text-color-muted-foreground hover:bg-muted hover:text-color-foreground transition-colors",
                narrowExpanded ? "md:flex" : "md:hidden",
                collapsed ? "xl:hidden" : "xl:flex",
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

          {((narrowExpanded ? systemGroupOpen : true) &&
            (collapsed ? true : systemGroupOpen)) && (
            <div className="space-y-1">{systemItems.map(renderItem)}</div>
          )}

          <div className="mt-auto pt-3 border-t border-border">
            <button
              type="button"
              onClick={logout}
              className={cn(
                "flex h-10 w-full items-center gap-3 rounded-surface px-3 text-style-body-strong text-color-muted-foreground transition-colors hover:bg-danger-subtle hover:text-color-danger",
                narrowExpanded
                  ? "md:justify-start md:px-3"
                  : "md:justify-center md:px-0",
                collapsed
                  ? "xl:justify-center xl:px-0"
                  : "xl:justify-start xl:px-3",
              )}
              title={!narrowExpanded || collapsed ? t("actions.logout") : undefined}
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
