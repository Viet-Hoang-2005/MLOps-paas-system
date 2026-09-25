import {
  Bell,
  Bot,
  BrainCircuit,
  GitBranch,
  KeyRound,
  Layers,
  LineChart,
  LogOut,
  Menu,
  Settings,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink, useLocation, matchPath } from "react-router-dom";
import { routes } from "@/app/router/paths";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { cn } from "@/shared/lib/cn";
import { projectPaths } from "@/app/router/paths";

interface DashboardSidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onToggle: () => void;
  onCloseMobile: () => void;
}

export default function Sidebar({
  collapsed,
  mobileOpen,
  onToggle,
  onCloseMobile,
}: DashboardSidebarProps) {
  const location = useLocation();
  const { logout } = useAuth();
  const { t } = useTranslation("common");

  // Detect if user is inside a specific project context
  const projectMatch = matchPath(
    "/dashboard/projects/:projectId/*",
    location.pathname,
  );
  const currentProjectId =
    projectMatch?.params.projectId && projectMatch.params.projectId !== "new"
      ? projectMatch.params.projectId
      : null;

  const itemClass = (active: boolean) =>
    cn(
      "group flex h-10 items-center gap-3 rounded-compact px-3 text-style-body-strong transition-colors focus-visible:ring-2 focus-visible:ring-ring",
      active
        ? "bg-primary text-color-primary-foreground"
        : "text-color-muted-foreground hover:bg-muted hover:text-color-foreground",
      "md:justify-center md:px-0 xl:justify-start xl:px-3",
      collapsed && "xl:justify-center xl:px-0",
    );

  const subItemClass = (active: boolean) =>
    cn(
      "group flex h-8 items-center gap-2 rounded-compact px-2.5 text-style-caption font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring",
      active
        ? "bg-primary/10 text-color-primary font-semibold"
        : "text-color-muted-foreground hover:bg-muted hover:text-color-foreground",
    );

  const labelClass = cn(
    "truncate md:hidden xl:block",
    collapsed && "xl:hidden",
  );

  const isProjectsActive = location.pathname.startsWith("/dashboard/projects");

  const projectSubItems = currentProjectId
    ? [
        {
          key: "overview",
          label: t("navigation.overview", "Overview"),
          to: projectPaths.overview(currentProjectId),
          icon: Layers,
          match: projectPaths.overview(currentProjectId),
        },
        {
          key: "deployment",
          label: t("navigation.deployment", "Deployment"),
          to: projectPaths.deployment(currentProjectId),
          icon: Bot,
          match: projectPaths.deployment(currentProjectId),
        },
        {
          key: "monitoring",
          label: t("navigation.monitoring", "Monitoring"),
          to: projectPaths.monitoring(currentProjectId),
          icon: LineChart,
          match: projectPaths.monitoring(currentProjectId),
        },
        {
          key: "training",
          label: t("navigation.training", "Training"),
          to: projectPaths.training(currentProjectId),
          icon: BrainCircuit,
          match: projectPaths.training(currentProjectId),
        },
        {
          key: "evolution",
          label: t("navigation.evolution", "Evolution"),
          to: `/dashboard/projects/${currentProjectId}/evolution`,
          icon: GitBranch,
          match: `/dashboard/projects/${currentProjectId}/evolution`,
        },
      ]
    : [];

  const utilityItems = [
    {
      key: "notification",
      label: t("navigation.notification", "Notification"),
      to: routes.notifications,
      icon: Bell,
      match: routes.notifications,
    },
    {
      key: "setting",
      label: t("navigation.setting", "Setting"),
      to: routes.profile,
      icon: Settings,
      match: "/dashboard/settings",
    },
    {
      key: "apiTokens",
      label: t("navigation.apiTokens", "API Token"),
      to: routes.apiTokens,
      icon: KeyRound,
      match: routes.apiTokens,
    },
  ] as const;

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
            {t("navigation.workspace")}
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

        <div className="hidden h-12 items-center gap-1 border-b border-border p-3 md:flex md:justify-center xl:justify-start">
          <button
            type="button"
            onClick={onToggle}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-surface text-color-muted-foreground hover:text-color-foreground"
            aria-label={
              collapsed
                ? t("actions.expandSidebar")
                : t("actions.collapseSidebar")
            }
          >
            <Menu className="h-5 w-5" />
          </button>
          <span
            className={cn(
              "text-style-body text-color-muted-foreground md:hidden xl:block",
              collapsed && "xl:hidden",
            )}
          >
            {t("navigation.workspace")}
          </span>
        </div>

        <nav
          className="flex min-h-0 flex-1 flex-col justify-between overflow-y-auto p-3"
          aria-label={t("navigation.primary")}
        >
          <div className="space-y-1">
            {/* Primary Model Projects Link */}
            <NavLink
              to={routes.projects}
              onClick={onCloseMobile}
              className={itemClass(isProjectsActive)}
              title={collapsed ? t("navigation.modelProjects") : undefined}
            >
              <Bot className="h-5 w-5 shrink-0" />
              <span className={labelClass}>{t("navigation.modelProjects")}</span>
            </NavLink>

            {/* Sub-items for active Project context */}
            {currentProjectId && !collapsed && (
              <div className="ml-3 my-1.5 space-y-0.5 border-l-2 border-border pl-2 md:hidden xl:block">
                {projectSubItems.map((sub) => {
                  const SubIcon = sub.icon;
                  const isSubActive = location.pathname.startsWith(sub.match);
                  return (
                    <NavLink
                      key={sub.key}
                      to={sub.to}
                      onClick={onCloseMobile}
                      className={subItemClass(isSubActive)}
                    >
                      <SubIcon className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{sub.label}</span>
                    </NavLink>
                  );
                })}
              </div>
            )}
          </div>

          {/* Utility items and Logout */}
          <div className="mb-2 space-y-1">
            {utilityItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname.startsWith(item.match);
              return (
                <NavLink
                  key={item.key}
                  to={item.to}
                  onClick={onCloseMobile}
                  className={itemClass(isActive)}
                  title={collapsed ? item.label : undefined}
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  <span className={labelClass}>{item.label}</span>
                </NavLink>
              );
            })}

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
