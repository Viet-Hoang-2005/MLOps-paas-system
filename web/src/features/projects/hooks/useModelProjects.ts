import { useQuery } from "@tanstack/react-query";
import { listModelProjects } from "@/features/projects/api/catalogApi";
import { catalogQueryKeys } from "@/features/projects/queryKeys";

export function useModelProjects() {
  return useQuery({
    queryKey: catalogQueryKeys.projects(),
    queryFn: listModelProjects,
    refetchInterval: 5000,
  });
}
