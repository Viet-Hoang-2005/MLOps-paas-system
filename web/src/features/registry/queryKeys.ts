export const registryQueryKeys = {
  all: ['registry'] as const,
  families: () => [...registryQueryKeys.all, 'families'] as const,
  family: (id: string) => [...registryQueryKeys.families(), id] as const,
  versions: (familyId: string) => [...registryQueryKeys.family(familyId), 'versions'] as const,
  version: (id: string) => [...registryQueryKeys.all, 'versions', id] as const,
  metrics: (familyId: string, versionId: string) =>
    [...registryQueryKeys.version(versionId), 'metrics', familyId] as const,
  history: (familyId: string) => [...registryQueryKeys.family(familyId), 'history'] as const,
};
