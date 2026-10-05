import { useMutation, useQueryClient } from "@tanstack/react-query";
import { registerBuild } from "@/features/deployments/api/lifecycleApi";
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
      await client.invalidateQueries({
        queryKey: deploymentFlowKeys.build(build.id),
      });
      await client.invalidateQueries({
        queryKey: deploymentFlowKeys.history(projectId),
      });
    },
  });
}
