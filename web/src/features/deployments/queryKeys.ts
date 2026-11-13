export const deploymentFlowKeys = {
  build: (id: string) => ["deployments", "build", id] as const,
  deployment: (id: string) => ["deployments", "deployment", id] as const,
  history: (id: string) => ["deployments", "history", id] as const,
  // Completed training jobs offered as build sources; each carries the output_revision a build must send.
  jobs: () => ["deployments", "training-sources"] as const,
  deployments: () => ["deployments", "all"] as const,
};
