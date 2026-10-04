import { useQuery } from "@tanstack/react-query";
import {
  getModelProject,
  getVersionSnapshot,
  getRunningSource,
} from "@/shared/api/catalogApi";
import { downloadText } from "@/shared/api/files";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";

export const projectOverviewKeys = {
  detail: (id: string) => ["projects", "overview", id] as const,
  asset: (url: string) => ["projects", "snapshot", url] as const,
  source: (projectId: string, versionId: string) =>
    ["projects", "running-source", projectId, versionId] as const,
  metrics: (projectId: string, deploymentId: string, window: string) =>
    ["projects", "runtime-metrics", projectId, deploymentId, window] as const,
};
export const useProjectOverview = (id?: string) =>
  useQuery({
    queryKey: projectOverviewKeys.detail(id ?? ""),
    queryFn: () => getModelProject(id!),
    enabled: Boolean(id),
    refetchInterval: 5000,
  });
export const useSnapshotText = (url?: string, snapshotId?: string) =>
  useQuery({
    queryKey: projectOverviewKeys.asset(snapshotId ?? url ?? ""),
    queryFn: ({ signal }) => downloadText(url!, signal),
    enabled: Boolean(url),
    staleTime: 60000,
  });
export const useRunningVersion = (id?: string) =>
  useQuery({
    queryKey: evolutionQueryKeys.snapshot(id ?? ""),
    queryFn: () => getVersionSnapshot(id!),
    enabled: Boolean(id),
  });
export const useRunningSource = (projectId?: string, versionId?: string) =>
  useQuery({
    queryKey: projectOverviewKeys.source(projectId ?? "", versionId ?? ""),
    queryFn: () => getRunningSource(projectId!),
    enabled: Boolean(projectId && versionId),
  });
