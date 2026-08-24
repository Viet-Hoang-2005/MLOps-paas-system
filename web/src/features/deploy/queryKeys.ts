export const deployQueryKeys = {
  all: ['deploy'] as const,
  builds: () => [...deployQueryKeys.all, 'builds'] as const,
  build: (id: string) => [...deployQueryKeys.builds(), id] as const,
  logs: (id: string) => [...deployQueryKeys.build(id), 'logs'] as const,
  deployments: () => [...deployQueryKeys.all, 'deployments'] as const,
  deployment: (id: string) => [...deployQueryKeys.deployments(), id] as const,
};
