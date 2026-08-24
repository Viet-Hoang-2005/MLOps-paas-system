export const catalogQueryKeys = {
  all: ['catalog'] as const,
  projects: () => [...catalogQueryKeys.all, 'projects'] as const,
  project: (id: string) => [...catalogQueryKeys.projects(), id] as const,
  endpointLogs: (id: string) => [...catalogQueryKeys.project(id), 'endpoint-logs'] as const,
  sourceFiles: (id: string) => [...catalogQueryKeys.project(id), 'source-files'] as const,
  referenceFiles: (id: string) => [...catalogQueryKeys.project(id), 'reference-files'] as const,
};
