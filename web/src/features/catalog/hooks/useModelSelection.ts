import { createContext, useContext } from 'react';
import type { ModelProject } from '@/features/catalog/types';

export type DashboardModel = ModelProject;

export interface ModelSelectionContextValue {
  models: DashboardModel[];
  selectedModel: DashboardModel | null;
  selectModel: (modelId: string) => void;
  loading: boolean;
}

export const ModelSelectionContext = createContext<ModelSelectionContextValue | undefined>(undefined);

export function useModelSelection() {
  const context = useContext(ModelSelectionContext);
  if (!context) {
    throw new Error('useModelSelection must be used inside ModelSelectionProvider.');
  }
  return context;
}
