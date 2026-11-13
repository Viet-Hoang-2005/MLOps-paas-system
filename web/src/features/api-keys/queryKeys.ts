export const apiTokenQueryKeys = {
  all: ["api-keys"] as const,
  apiKeys: () => [...apiTokenQueryKeys.all, "keys"] as const,
};
