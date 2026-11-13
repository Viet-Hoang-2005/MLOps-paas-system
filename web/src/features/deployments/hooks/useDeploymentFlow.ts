import { useQuery } from "@tanstack/react-query";
import {
  getBuild,
  listProjectBuilds,
  listDeployments,
} from "@/features/deployments/api/deployApi";
import { getDeployment } from "@/features/deployments/api/lifecycleApi";
import { listTrainingJobs } from "@/features/training/api/trainingApi";

import { deploymentFlowKeys } from "@/features/deployments/queryKeys";

export { deploymentFlowKeys };
export const useBuild = (id: string | null) =>
  useQuery({
    queryKey: deploymentFlowKeys.build(id ?? ""),
    queryFn: () => getBuild(id!),
    enabled: Boolean(id),
    refetchInterval: 2000,
  });
export const useDeployment = (id: string | null) =>
  useQuery({
    queryKey: deploymentFlowKeys.deployment(id ?? ""),
    queryFn: () => getDeployment(id!),
    enabled: Boolean(id),
    refetchInterval: 2000,
  });
export const useBuildHistory = (id?: string) =>
  useQuery({
    queryKey: deploymentFlowKeys.history(id ?? ""),
    queryFn: () => listProjectBuilds(id!),
    enabled: Boolean(id),
    refetchInterval: 5000,
  });
export const useBuildTrainingSources = () =>
  useQuery({
    queryKey: deploymentFlowKeys.jobs(),
    queryFn: listTrainingJobs,
    // The output_revision in this list must match the server's when a build starts, and it
    // changes whenever outputs are edited elsewhere; never trust a cached copy on entry.
    refetchOnMount: "always",
  });
export const useDeployments = () =>
  useQuery({
    queryKey: deploymentFlowKeys.deployments(),
    queryFn: listDeployments,
    refetchInterval: 5000,
  });
