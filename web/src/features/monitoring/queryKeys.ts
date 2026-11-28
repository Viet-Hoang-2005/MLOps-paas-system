export const driftQueryKeys = {
  all: ["drift"] as const,
  monitors: (modelId: string) =>
    [...driftQueryKeys.all, "monitors", modelId] as const,
  productionData: (modelId: string, versionId?: string, limit = 100) =>
    [
      ...driftQueryKeys.all,
      "production-data",
      modelId,
      versionId ?? "",
      limit,
    ] as const,
  detail: (monitorId: string) =>
    [...driftQueryKeys.all, "detail", monitorId] as const,
  reference: (monitorId: string) =>
    [...driftQueryKeys.all, "reference", monitorId] as const,
  uploadPreview: (id: string) =>
    [...driftQueryKeys.all, "upload-preview", id] as const,
  referenceFiles: (modelId: string) =>
    [...driftQueryKeys.all, "reference-files", modelId] as const,
  reportData: (runId: string) =>
    [...driftQueryKeys.all, "report-data", runId] as const,
};
