export const driftQueryKeys = {
  all: ['drift'] as const,
  monitors: (modelId: string) => [...driftQueryKeys.all, 'monitors', modelId] as const,
  results: (jobId: string) => [...driftQueryKeys.all, 'results', jobId] as const,
  productionData: (modelId: string) => [...driftQueryKeys.all, 'production-data', modelId] as const,
  referenceFiles: (modelId: string) => [...driftQueryKeys.all, 'reference-files', modelId] as const,
};
