import { ModelProjectTable } from "@/features/projects/components/ModelProjectTable";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Button } from "@/shared/components/Button";
import { Callout } from "@/shared/components/Callout";
import { PageHeader } from "@/shared/components/PageHeader";
import { Search } from "@/shared/components/Search";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export default function ModelProjectPage() {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const projects = useModelProjects();
  const [searchQuery, setSearchQuery] = useState("");

  const filteredProjects = useMemo(() => {
    const allProjects = projects.data?.models ?? [];
    const query = searchQuery.trim().toLowerCase();
    if (!query) return allProjects;
    return allProjects.filter((project) => {
      const name = project.name?.toLowerCase() ?? "";
      const description = project.description?.toLowerCase() ?? "";
      const flavor = project.flavor?.toLowerCase() ?? "";
      return (
        name.includes(query) ||
        description.includes(query) ||
        flavor.includes(query)
      );
    });
  }, [projects.data?.models, searchQuery]);

  return (
    <div className="space-y-6">
      <PageHeader title={t("workflow.projects")} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Search
          wrapperClassName="w-full sm:w-80"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          onClear={() => setSearchQuery("")}
          placeholder={t("workflow.search")}
          clearAriaLabel={t("workflow.clearSearch")}
        />
        <Button
          size="md"
          icon={<Plus className="h-4 w-4" />}
          onClick={() => navigate("/dashboard/projects/new")}
        >
          {t("workflow.newProject")}
        </Button>
      </div>
      {projects.isError && (
        // A failed background refresh keeps the last loaded list on screen; only a failed
        // first load, with nothing to show, replaces the table.
        <Callout
          variant="danger"
          role="alert"
          description={`${projects.data ? `${t("workflow.staleData")} ` : ""}${getApiErrorMessage(projects.error, t("workflow.failed"))}`}
          action={
            <Button
              size="sm"
              variant="secondary"
              loading={projects.isFetching}
              onClick={() => void projects.refetch()}
            >
              {t("workflow.retryLoad")}
            </Button>
          }
        />
      )}
      {!(projects.isError && !projects.data) && (
        <ModelProjectTable
          data={filteredProjects}
          loading={projects.isLoading}
          emptyMessage={
            searchQuery.trim() ? t("workflow.noMatches") : undefined
          }
          onRefresh={() => projects.refetch()}
        />
      )}
    </div>
  );
}
