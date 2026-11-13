import { useMutation, useQueryClient } from "@tanstack/react-query";
import { registerBuild } from "@/features/deployments/api/lifecycleApi";
import { overviewQueryKeys } from "@/features/overview/queryKeys";
import { catalogQueryKeys } from "@/features/projects/queryKeys";
import { deploymentFlowKeys } from "./useDeploymentFlow";

export function useBuildRegistration(
  buildId: string | null,
  projectId: string,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => registerBuild(buildId!),
    onSuccess: async (build) => {
      client.setQueryData(deploymentFlowKeys.build(build.id), build);
      await Promise.all([
        client.invalidateQueries({
          queryKey: deploymentFlowKeys.build(build.id),
        }),
        client.invalidateQueries({
          queryKey: deploymentFlowKeys.history(projectId),
        }),
        client.invalidateQueries({
          queryKey: overviewQueryKeys.detail(projectId),
        }),
        client.invalidateQueries({
          queryKey: overviewQueryKeys.attributes(projectId),
        }),
        client.invalidateQueries({
          queryKey: catalogQueryKeys.projects(),
        }),
      ]);
    },
  });
}
