export function createMockUser(overrides: Record<string, unknown> = {}) {
  return {
    id: "user-1",
    email: "developer@example.com",
    username: "developer",
    first_name: "Dev",
    last_name: "User",
    is_active: true,
    avatar_url: null,
    tenant_id: "tenant-default",
    ...overrides,
  };
}

