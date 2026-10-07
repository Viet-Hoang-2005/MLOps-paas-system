import { useQuery } from "@tanstack/react-query";
import {
  getModelProject,
  getVersionSnapshot,
  getRunningSource,
  getRunningAttributes,
} from "@/shared/api/catalogApi";
import { downloadText } from "@/shared/api/files";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import { overviewQueryKeys } from "@/features/overview/queryKeys";

export {
  overviewQueryKeys,
  overviewQueryKeys as projectOverviewKeys,
} from "@/features/overview/queryKeys";

export const useProjectOverview = (id?: string) =>
  useQuery({
    queryKey: overviewQueryKeys.detail(id ?? ""),
    queryFn: () => getModelProject(id!),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data?.active_endpoint?.deployment_status === "succeeded"
        ? 5000
        : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    retry: false,
  });

export const useSnapshotText = (url?: string, snapshotId?: string) =>
  useQuery({
    queryKey: overviewQueryKeys.asset(snapshotId ?? url ?? ""),
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
    queryKey: overviewQueryKeys.source(projectId ?? "", versionId ?? ""),
    queryFn: () => getRunningSource(projectId!),
    enabled: Boolean(projectId && versionId),
  });

export const useRunningAttributes = (projectId?: string, versionId?: string) =>
  useQuery({
    queryKey: overviewQueryKeys.attributes(projectId ?? "", versionId ?? ""),
    queryFn: () => getRunningAttributes(projectId!),
    enabled: Boolean(projectId && versionId),
  });

