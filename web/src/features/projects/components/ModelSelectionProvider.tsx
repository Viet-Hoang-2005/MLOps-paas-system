import { useMemo, useState, useEffect, type ReactNode } from "react";
import { useLocation, useNavigate, matchPath } from "react-router-dom";
import { useModelProjects } from "@/features/projects/hooks/useModelProjects";
import {
  ModelSelectionContext,
  type ModelSelectionContextValue,
} from "@/features/projects/hooks/useModelSelection";
import { projectSelectionPath } from "@/features/projects/navigation";

export function ModelSelectionProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const match = matchPath("/dashboard/projects/:modelId/*", location.pathname);
  const urlModelId = match?.params.modelId;
  const [localModelId, setLocalModelId] = useState<string | null>(() =>
    localStorage.getItem("selected_model_project_id"),
  );
  const { data, isLoading } = useModelProjects();
  const models = useMemo(() => data?.models ?? [], [data?.models]);
  const selectedModel =
    models.find((model) => model.id === (urlModelId || localModelId)) ??
    (urlModelId ? null : (models[0] ?? null));
  useEffect(() => {
    if (urlModelId && models.some((model) => model.id === urlModelId))
      localStorage.setItem("selected_model_project_id", urlModelId);
  }, [models, urlModelId]);
  const value = useMemo<ModelSelectionContextValue>(
    () => ({
      models,
      selectedModel,
      loading: isLoading,
      selectModel: (modelId: string) => {
        setLocalModelId(modelId);
        localStorage.setItem("selected_model_project_id", modelId);
        navigate(projectSelectionPath(location.pathname, modelId));
      },
    }),
    [models, selectedModel, isLoading, location.pathname, navigate],
  );
  return (
    <ModelSelectionContext.Provider value={value}>
      {children}
    </ModelSelectionContext.Provider>
  );
}
