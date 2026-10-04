import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { ColumnDef } from "@tanstack/react-table";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import type { ModelProject } from "@/features/projects/types";
import { Button } from "@/shared/components/Button";
import { Badge } from "@/shared/components/Badge";
import { DataTable } from "@/shared/components/DataTable";
import { PageHeader } from "@/shared/components/PageHeader";
import { getApiErrorMessage } from "@/shared/api/errors";
import { Plus } from "lucide-react";

export default function ProjectListPage() {
  const { t, i18n } = useTranslation("projects");
  const navigate = useNavigate();
  const projects = useModelProjects();
  const columns: ColumnDef<ModelProject>[] = [
    {
      accessorKey: "name",
      header: t("workflow.name"),
      cell: ({ row }) => (
        <button
          type="button"
          className="text-color-primary hover:underline"
          onClick={() =>
            navigate(`/dashboard/projects/${row.original.id}/overview`)
          }
        >
          {row.original.name}
        </button>
      ),
    },
    { accessorKey: "description", header: t("workflow.description") },
    { accessorKey: "flavor", header: t("flavor") },
    {
      accessorKey: "lifecycle_status",
      header: t("workflow.status"),
      cell: ({ row }) => (
        <Badge>
          {t(
            `workflow.${row.original.deletion_state !== "active" ? row.original.deletion_state : (row.original.lifecycle_status ?? "preview")}`,
          )}
        </Badge>
      ),
    },
    {
      accessorKey: "updated_at",
      header: t("updated"),
      cell: ({ row }) =>
        new Date(row.original.updated_at).toLocaleString(i18n.language),
    },
  ];
  return (
    <div className="space-y-6">
      <PageHeader
        title={t("workflow.projects")}
        actions={
          <Button
            size={"md"}
            icon={<Plus className="h-4 w-4" />}
            onClick={() => navigate("/dashboard/projects/new")}
          >
            {t("workflow.newProject")}
          </Button>
        }
      />
      {projects.isError ? (
        <p role="alert">
          {getApiErrorMessage(projects.error, t("workflow.failed"))}
        </p>
      ) : (
        <DataTable
          columns={columns}
          data={projects.data?.models ?? []}
          loading={projects.isLoading}
        />
      )}
    </div>
  );
}
