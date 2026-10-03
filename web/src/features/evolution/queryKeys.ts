export const evolutionQueryKeys = {
  all: ["evolution"] as const,
  versions: (projectId: string) =>
    [...evolutionQueryKeys.all, "versions", projectId] as const,
  snapshot: (versionId: string) =>
    [...evolutionQueryKeys.all, "snapshot", versionId] as const,
};
