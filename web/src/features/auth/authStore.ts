let currentAccessToken: string | null = null;
let currentTenantId: string | null = null;

export const getAccessToken = (): string | null => currentAccessToken;

export const getTenantId = (): string | null => currentTenantId;

export const isAuthenticated = (): boolean => Boolean(currentAccessToken);

export const setAuthTokens = (tokens: {
  access: string;
  tenantId?: string;
}): void => {
  currentAccessToken = tokens.access;
  if (tokens.tenantId) {
    currentTenantId = tokens.tenantId;
  }
};

export const clearAuthStore = (): void => {
  currentAccessToken = null;
  currentTenantId = null;
  if (typeof window !== "undefined" && window.localStorage) {
    window.localStorage.removeItem("access_token");
    window.localStorage.removeItem("refresh_token");
    window.localStorage.removeItem("tenant_id");
  }
};

