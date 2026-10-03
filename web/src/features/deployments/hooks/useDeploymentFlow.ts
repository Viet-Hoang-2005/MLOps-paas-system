import { useQuery } from "@tanstack/react-query";
import {
  getBuild,
  listProjectBuilds,
  listDeployments,
} from "@/features/deployments/api/deployApi";
import { getDeployment } from "@/features/deployments/api/lifecycleApi";
import { listTrainingJobs } from "@/features/training/api/trainingApi";

export const deploymentFlowKeys = {
  build: (id: string) => ["deployments", "build", id] as const,
  deployment: (id: string) => ["deployments", "deployment", id] as const,
  history: (id: string) => ["deployments", "history", id] as const,
  jobs: () => ["deployments", "training-sources"] as const,
  deployments: () => ["deployments", "all"] as const,
};
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
  useQuery({ queryKey: deploymentFlowKeys.jobs(), queryFn: listTrainingJobs });
export const useDeployments = () =>
  useQuery({
    queryKey: deploymentFlowKeys.deployments(),
    queryFn: listDeployments,
    refetchInterval: 5000,
  });
