import { useMemo, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { useLocation, useNavigate, matchPath } from 'react-router-dom';
import { useModelProjects } from '@/features/catalog/hooks/useModelProjects';
import { ModelSelectionContext } from '@/features/catalog/hooks/useModelSelection';
import type { ModelSelectionContextValue } from '@/features/catalog/hooks/useModelSelection';

export function ModelSelectionProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();

  const match = useMemo(() => {
    const routeMatch = matchPath("/dashboard/home/models/:modelId", location.pathname) ||
      matchPath("/dashboard/home/model-testing/:modelId", location.pathname) ||
      matchPath("/dashboard/drift-monitoring/:modelId/new", location.pathname) ||
      matchPath("/dashboard/drift-monitoring/:modelId/report/:runId", location.pathname) ||
      matchPath("/dashboard/drift-monitoring/:modelId", location.pathname) ||
      matchPath("/dashboard/model-training/:modelId", location.pathname) ||
      matchPath("/dashboard/management/model/:modelId/:tab", location.pathname) ||
      matchPath("/dashboard/model-evolution/:modelId", location.pathname);
    return routeMatch?.params.modelId === 'upload' ? null : routeMatch;
  }, [location.pathname]);

  const urlModelId = match?.params.modelId ? match.params.modelId : null;

  const [localModelId, setLocalModelId] = useState<string | null>(() => {
    const stored = localStorage.getItem('selected_model_project_id');
    return stored ? stored : null;
  });

  const { data, isLoading } = useModelProjects();
  const models = useMemo(() => data?.models ?? [], [data?.models]);

  const activeModelId = urlModelId || localStorage.getItem('selected_model_project_id') || localModelId;
  const selectedModel = models.find((model) => model.id === activeModelId) ?? models[0] ?? null;

  useEffect(() => {
    if (!urlModelId || !models.some((model) => model.id === urlModelId)) return;
    localStorage.setItem('selected_model_project_id', urlModelId);
  }, [models, urlModelId]);

  const value = useMemo<ModelSelectionContextValue>(() => {
    return {
      models,
      selectedModel,
      selectModel: (modelId: string) => {
        setLocalModelId(modelId);
        localStorage.setItem('selected_model_project_id', modelId);
        
        if (match && urlModelId) {
          const nextPath = location.pathname.replace(`/${urlModelId}`, `/${modelId}`);
          navigate(`${nextPath}${location.search}${location.hash}`);
        } else {
          const supportedBases = ['/dashboard/home/models', '/dashboard/home/model-testing', '/dashboard/drift-monitoring', '/dashboard/model-training', '/dashboard/model-evolution'];
          const base = supportedBases.find(b => location.pathname === b || location.pathname === `${b}/`);
          if (base) {
             navigate(`${base}/${modelId}${location.search}${location.hash}`);
          }
        }
      },
      loading: isLoading,
    };
  }, [isLoading, models, selectedModel, match, location, navigate, urlModelId]);

  // Auto-redirect if on a supported base path without a model ID
  useEffect(() => {
    if (!selectedModel) return;
    
    const supportedBases = [
      '/dashboard/home/models',
      '/dashboard/home/model-testing',
      '/dashboard/drift-monitoring',
      '/dashboard/model-training',
      '/dashboard/model-evolution'
    ];
    
    const baseMatch = supportedBases.find(b => location.pathname === b || location.pathname === `${b}/`);
    if (baseMatch) {
      navigate(`${baseMatch}/${selectedModel.id}${location.search}${location.hash}`, { replace: true });
      return;
    }

    if (urlModelId && !models.some((model) => model.id === urlModelId)) {
      const nextPath = location.pathname.replace(`/${urlModelId}`, `/${selectedModel.id}`);
      navigate(`${nextPath}${location.search}${location.hash}`, { replace: true });
    }
  }, [location.pathname, location.search, location.hash, models, navigate, selectedModel, urlModelId]);

  return (
    <ModelSelectionContext.Provider value={value}>
      {children}
    </ModelSelectionContext.Provider>
  );
}
