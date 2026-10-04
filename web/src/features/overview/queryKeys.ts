export const overviewQueryKeys = {
  all: ["overview"] as const,
  detail: (id: string) => [...overviewQueryKeys.all, "detail", id] as const,
  asset: (url: string) => [...overviewQueryKeys.all, "asset", url] as const,
  source: (projectId: string, versionId: string) =>
    [...overviewQueryKeys.all, "source", projectId, versionId] as const,
  metrics: (projectId: string, deploymentId: string, window: string) =>
    [...overviewQueryKeys.all, "metrics", projectId, deploymentId, window] as const,
};

export const projectOverviewKeys = overviewQueryKeys;
