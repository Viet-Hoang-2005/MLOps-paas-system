export const settingsQueryKeys = {
  all: ["settings"] as const,
  profile: () => [...settingsQueryKeys.all, "profile"] as const,
};
