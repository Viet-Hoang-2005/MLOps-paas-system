import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  deleteBuildById,
  rebuildById,
} from "@/features/deployments/api/deployApi";
import { deploymentFlowKeys } from "./useDeploymentFlow";

export function useBuildActions(projectId?: string) {
  const client = useQueryClient();
  const invalidate = async (id: string) => {
    await Promise.all([
      client.invalidateQueries({
        queryKey: deploymentFlowKeys.history(projectId ?? ""),
      }),
      client.invalidateQueries({ queryKey: deploymentFlowKeys.build(id) }),
    ]);
  };
  const rebuild = useMutation({
    mutationFn: rebuildById,
    onSuccess: async (build) => {
      client.setQueryData(deploymentFlowKeys.build(build.id), build);
      await invalidate(build.id);
    },
  });
  const remove = useMutation({
    mutationFn: deleteBuildById,
    onSuccess: async (build) => {
      client.setQueryData(deploymentFlowKeys.build(build.id), build);
      await invalidate(build.id);
    },
  });
  return { rebuild, remove };
}
