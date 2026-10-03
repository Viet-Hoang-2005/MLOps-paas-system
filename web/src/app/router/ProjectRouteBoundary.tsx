import { Outlet, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import { RouteFallback } from "./RouteFallback";
import NotFoundPage from "./NotFoundPage";

export default function ProjectRouteBoundary() {
  const { modelId } = useParams();
  const { t } = useTranslation("projects");
  const projects = useModelProjects();
  if (projects.isPending) return <RouteFallback />;
  if (projects.isError) return <p role="alert">{t("workflow.failed")}</p>;
  if (!projects.data?.models.some((project) => project.id === modelId))
    return <NotFoundPage />;
  return <Outlet key={modelId} />;
}
