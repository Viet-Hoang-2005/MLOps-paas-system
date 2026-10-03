export const apiTokenQueryKeys = {
  all: ["api-tokens"] as const,
  apiKeys: () => [...apiTokenQueryKeys.all, "keys"] as const,
};
