import {
  ArrowLeft,
  Bot,
  BrainCircuit,
  GitBranch,
  LineChart,
  Layers,
  Edit3,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useParams,
} from "react-router-dom";
import { useProjectOverview } from "@/features/catalog/hooks/useModelProjects";
import { Badge } from "@/shared/components/Badge";
import { Button } from "@/shared/components/Button";
import { cn } from "@/shared/lib/cn";
import EditModelModal from "@/features/deploy/components/EditModelModal";
import type { ModelProject } from "@/features/catalog/types";
import { projectPaths } from "@/app/router/paths";

export default function ProjectLayout() {
  const { projectId } = useParams<{ projectId: string }>();
  const location = useLocation();
  const { t } = useTranslation("catalog");
  const { data: overview, isLoading, error, refetch } = useProjectOverview(projectId);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-style-body text-color-muted-foreground">
          {t("statuses.loading", "Loading project...")}
        </p>
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-surface border border-border bg-surface p-12 text-center">
        <h2 className="text-style-section-title text-color-foreground">
          {t("errors.notFoundTitle", "Project not found")}
        </h2>
        <p className="max-w-md text-style-body text-color-muted-foreground">
          {t(
            "errors.notFoundDescription",
            "The requested model project could not be found or you do not have permission to view it.",
          )}
        </p>
        <Link to="/dashboard/projects">
          <Button variant="secondary">
            <ArrowLeft className="mr-2 h-4 w-4" />
            {t("actions.backToProjects", "Back to Projects")}
          </Button>
        </Link>
      </div>
    );
  }

  const { project, present, draft } = overview;

  const tabs = [
    {
      label: t("navigation.overview", "Overview"),
      to: projectPaths.overview(projectId!),
      icon: Layers,
      match: projectPaths.overview(projectId!),
    },
    {
      label: t("navigation.deployment", "Deployment"),
      to: projectPaths.deployment(projectId!),
      icon: Bot,
      match: projectPaths.deployment(projectId!),
    },
    {
      label: t("navigation.monitoring", "Monitoring"),
      to: projectPaths.monitoring(projectId!),
      icon: LineChart,
      match: projectPaths.monitoring(projectId!),
    },
    {
      label: t("navigation.training", "Training"),
      to: projectPaths.training(projectId!),
      icon: BrainCircuit,
      match: projectPaths.training(projectId!),
    },
    {
      label: t("navigation.evolution", "Evolution"),
      to: projectPaths.evolution(projectId!),
      icon: GitBranch,
      match: projectPaths.evolution(projectId!),
    },
  ];

  // Adapter for EditModelModal compatibility
  const modelAdapter: ModelProject = {
    id: project.id,
    name: project.name,
    description: project.description,
    access_mode: project.access_mode,
    is_active: true,
    created_at: project.created_at,
    updated_at: project.updated_at,
  };

  return (
    <div className="flex flex-1 flex-col space-y-6">
      {/* Project Header */}
      <header className="flex flex-col gap-4 border-b border-border pb-0">
        <div>
          <Link
            to="/dashboard/projects"
            className="inline-flex min-h-8 items-center gap-2 text-style-caption text-color-muted-foreground hover:text-color-foreground focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            {t("actions.backToProjects", "All Projects")}
          </Link>

          <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-style-page-title text-color-foreground">
                {project.name}
              </h1>
              <button
                type="button"
                onClick={() => setIsEditModalOpen(true)}
                className="rounded-compact p-1 text-color-muted-foreground hover:bg-muted hover:text-color-foreground"
                title={t("actions.editProject", "Edit project info")}
              >
                <Edit3 className="h-4 w-4" />
              </button>

              <Badge variant={project.access_mode === "public" ? "primary" : "neutral"}>
                {project.access_mode}
              </Badge>

              {project.task_domain && (
                <Badge variant="neutral">{project.task_domain}</Badge>
              )}

              {present.has_production ? (
                <Badge variant="success" className="gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-current animate-pulse" />
                  {t("project.production", { version: present.version, defaultValue: `Production: ${present.version}` })}
                </Badge>
              ) : (
                <Badge variant="neutral">{t("project.noProduction", "No Production")}</Badge>
              )}

              {draft && (
                <Badge
                  variant={
                    draft.status === "ready"
                      ? "primary"
                      : draft.status === "locked"
                        ? "warning"
                        : "neutral"
                  }
                >
                  {t("project.draft", { status: draft.status, defaultValue: `Draft: ${draft.status}` })}{" "}
                  {draft.is_dirty ? t("project.unsaved", "• Unsaved") : ""}
                </Badge>
              )}
            </div>
          </div>

          {project.description && (
            <p className="mt-1 max-w-3xl text-style-body text-color-muted-foreground">
              {project.description}
            </p>
          )}
        </div>

        {/* Project Navigation Tabs */}
        <nav
          className="-mb-px flex space-x-2 overflow-x-auto border-t border-border pt-2"
          aria-label={t("project.tabsAriaLabel", "Project tabs")}
        >
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = location.pathname.startsWith(tab.match);
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={cn(
                  "inline-flex h-10 items-center gap-2 border-b-2 px-3 text-style-body-strong transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                  isActive
                    ? "border-primary text-color-primary"
                    : "border-transparent text-color-muted-foreground hover:border-border hover:text-color-foreground",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="whitespace-nowrap">{tab.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </header>

      {/* Child Route Content */}
      <main className="flex-1">
        <Outlet context={{ overview, isLoading, refetch }} />
      </main>

      {/* Edit Modal */}
      {isEditModalOpen && (
        <EditModelModal
          model={modelAdapter}
          visible={isEditModalOpen}
          onClose={() => {
            setIsEditModalOpen(false);
            refetch();
          }}
        />
      )}
    </div>
  );
}
