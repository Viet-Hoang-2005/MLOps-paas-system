import { useOutletContext } from "react-router-dom";
import type { ModelProjectOverviewResponse } from "@/features/catalog/types";

export interface ProjectOutletContext {
  overview: ModelProjectOverviewResponse;
  isLoading: boolean;
  refetch: () => void;
}

export function useProjectContext() {
  return useOutletContext<ProjectOutletContext>();
}
