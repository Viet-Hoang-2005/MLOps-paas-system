import { useQuery } from "@tanstack/react-query";
import { getProjectVersions } from "@/features/deployments/api/deployApi";
import { useBuildHistory } from "@/features/deployments/hooks/useDeploymentFlow";
import { useProjectOverview } from "@/features/overview/hooks/useProjectOverview";
import { useDriftMonitoringJobs } from "@/features/monitoring/hooks/useDriftMonitoring";
import { getVersionDetail } from "@/features/evolution/api/evolutionApi";
import { evolutionQueryKeys } from "@/features/evolution/queryKeys";
import {
  registeredVersionBuild,
  runningVersionId,
  selectEvolutionVersion,
} from "@/features/evolution/evolutionState";

export function useEvolution(projectId: string, requestedId: string | null) {
  const versions = useQuery({
    queryKey: evolutionQueryKeys.versions(projectId),
    queryFn: () => getProjectVersions(projectId),
    enabled: Boolean(projectId),
  });
  const project = useProjectOverview(projectId);
  const builds = useBuildHistory(projectId);
  const monitors = useDriftMonitoringJobs(projectId);
  const runningId = runningVersionId(project.data);
  const selected = selectEvolutionVersion(
    versions.data ?? [],
    requestedId,
    runningId,
  );
  const detail = useQuery({
    queryKey: evolutionQueryKeys.snapshot(selected?.id ?? ""),
    queryFn: ({ signal }) => getVersionDetail(selected!.id, signal),
    enabled: Boolean(selected),
  });
  // Never render a response from another project, including cached detail.
  const version =
    detail.data?.project_id === projectId && detail.data.id === selected?.id
      ? detail.data
      : undefined;
  return {
    versions,
    project,
    builds,
    monitors,
    detail,
    version,
    selected,
    runningId,
    build: version
      ? builds.data?.find(
          (build) =>
            build.project_id === projectId && build.version_id === version.id,
        )
      : undefined,
    deployableBuild: version
      ? registeredVersionBuild(builds.data ?? [], version)
      : undefined,
    loading: versions.isLoading || project.isLoading,
    error: versions.error || project.error,
    refresh: () =>
      Promise.all([
        versions.refetch(),
        project.refetch(),
        builds.refetch(),
        detail.isEnabled ? detail.refetch() : Promise.resolve(),
        monitors.refetch(),
      ]),
  };
}
