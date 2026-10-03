export const settingsQueryKeys = {
  all: ["settings"] as const,
  profile: () => [...settingsQueryKeys.all, "profile"] as const,
  avatars: () => [...settingsQueryKeys.profile(), "avatars"] as const,
};
