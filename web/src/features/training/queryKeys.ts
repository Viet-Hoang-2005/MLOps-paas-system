export const trainingQueryKeys = {
  all: ["training"] as const,
  jobs: () => [...trainingQueryKeys.all, "jobs"] as const,
  job: (id: string) => [...trainingQueryKeys.jobs(), id] as const,
  modelOutput: (id: string) => [...trainingQueryKeys.job(id), "model-output"] as const,
  referencePreview: (id: string) => [...trainingQueryKeys.job(id), "reference-preview"] as const,
  logs: (id: string) => [...trainingQueryKeys.job(id), "logs"] as const,
  metrics: (id: string) => [...trainingQueryKeys.job(id), "metrics"] as const,
  events: (id: string) => [...trainingQueryKeys.job(id), "events"] as const,
  usage: () => [...trainingQueryKeys.all, "usage"] as const,
};

