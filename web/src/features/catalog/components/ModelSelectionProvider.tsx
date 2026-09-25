import { useMemo, useState, useEffect } from "react";
import type { ReactNode } from "react";
import { useLocation, useNavigate, matchPath } from "react-router-dom";
import { useModelProjects } from "@/features/catalog/hooks/useModelProjects";
import { ModelSelectionContext } from "@/features/catalog/hooks/useModelSelection";
import type { ModelSelectionContextValue } from "@/features/catalog/hooks/useModelSelection";

export function ModelSelectionProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();

  // Read project context from the canonical route.
  const projectMatch = useMemo(() => {
    const match = matchPath(
      "/dashboard/projects/:projectId/*",
      location.pathname,
    );
    return match?.params.projectId && match.params.projectId !== "new"
      ? match
      : null;
  }, [location.pathname]);

  const urlModelId = projectMatch?.params.projectId || null;

  const [localModelId, setLocalModelId] = useState<string | null>(() => {
    const stored = localStorage.getItem("selected_model_project_id");
    return stored ? stored : null;
  });

  const { data, isLoading } = useModelProjects();
  const models = useMemo(() => data?.models ?? [], [data?.models]);

  const activeModelId =
    urlModelId ||
    localStorage.getItem("selected_model_project_id") ||
    localModelId;
  const selectedModel =
    models.find((model) => model.id === activeModelId) ?? models[0] ?? null;

  useEffect(() => {
    if (!urlModelId || !models.some((model) => model.id === urlModelId)) return;
    localStorage.setItem("selected_model_project_id", urlModelId);
  }, [models, urlModelId]);

  const value = useMemo<ModelSelectionContextValue>(() => {
    return {
      models,
      selectedModel,
      selectModel: (modelId: string) => {
        setLocalModelId(modelId);
        localStorage.setItem("selected_model_project_id", modelId);

        // If inside a project sub-page, preserve the sub-page route
        if (projectMatch && urlModelId) {
          const nextPath = location.pathname.replace(
            `/dashboard/projects/${urlModelId}`,
            `/dashboard/projects/${modelId}`,
          );
          navigate(`${nextPath}${location.search}${location.hash}`);
        } else {
          // If on a top-level page (e.g. /dashboard/projects), navigate to the selected model's overview
          navigate(`/dashboard/projects/${modelId}/overview`);
        }
      },
      loading: isLoading,
    };
  }, [
    isLoading,
    models,
    selectedModel,
    projectMatch,
    location,
    navigate,
    urlModelId,
  ]);

  return (
    <ModelSelectionContext.Provider value={value}>
      {children}
    </ModelSelectionContext.Provider>
  );
}
