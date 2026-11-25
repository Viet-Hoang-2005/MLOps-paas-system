let currentAccessToken: string | null = null;
let currentTenantId: string | null = null;
let sessionVersion = 0;

const LEGACY_AUTH_KEYS = ["access_token", "refresh_token", "tenant_id"];

export const clearLegacyAuthStorage = (): void => {
  if (typeof window === "undefined") return;

  try {
    const storage = window.localStorage;
    for (const key of LEGACY_AUTH_KEYS) storage.removeItem(key);
  } catch {
    // Authentication no longer depends on browser storage.
  }
};

clearLegacyAuthStorage();

export const getAccessToken = (): string | null => currentAccessToken;

export const getTenantId = (): string | null => currentTenantId;

export const getAuthSessionVersion = (): number => sessionVersion;

export const isAuthenticated = (): boolean => Boolean(currentAccessToken);

type SessionResetListener = () => void;
const sessionResetListeners = new Set<SessionResetListener>();

/** Runs when the session is cleared or switches to a different tenant. */
export const onAuthSessionReset = (
  listener: SessionResetListener,
): (() => void) => {
  sessionResetListeners.add(listener);
  return () => {
    sessionResetListeners.delete(listener);
  };
};

const notifySessionReset = (): void => {
  for (const listener of sessionResetListeners) listener();
};

export const setAuthSession = (
  session: {
    access: string;
    tenantId?: string;
  },
  { refresh = false } = {},
): void => {
  const previousTenantId = currentTenantId;
  const hadSession = currentAccessToken !== null;
  currentAccessToken = session.access;
  currentTenantId = session.tenantId ?? null;
  const tenantChanged = previousTenantId !== currentTenantId;
  if (!refresh || !hadSession || tenantChanged) {
    sessionVersion += 1;
  }
  // A silent refresh keeps the tenant; a different one means another account signed in
  // (for example from another tab sharing the refresh cookie).
  if (hadSession && tenantChanged) {
    notifySessionReset();
  }
};

export const clearAuthSession = (): void => {
  sessionVersion += 1;
  currentAccessToken = null;
  currentTenantId = null;
  clearLegacyAuthStorage();
  notifySessionReset();
};
