import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getRuntimeMetrics } from "@/features/overview/api/metricsApi";
import { overviewQueryKeys } from "@/features/overview/queryKeys";
import { createRealtimeSession } from "@/features/overview/realtimeMetrics";

export function useRuntimeMetrics(
  projectId: string,
  deploymentId: string,
  window: string,
) {
  const collect = useMemo(
    () => createRealtimeSession(deploymentId),
    [deploymentId],
  );
  return useQuery({
    queryKey: overviewQueryKeys.metrics(projectId, deploymentId, window),
    queryFn: async ({ signal }) => {
      try {
        const data = await getRuntimeMetrics(projectId, window, signal);
        return { ...data, points: collect(data) };
      } catch (error) {
        collect({
          mode: "realtime",
          status: "unavailable",
          deployment_id: deploymentId,
          snapshot: null,
        });
        throw error;
      }
    },
    enabled: Boolean(deploymentId),
    refetchInterval: (query) =>
      query.state.data?.mode === "history" ? 15000 : 5000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    retry: false,
    gcTime: 0,
    staleTime: 0,
  });
}
