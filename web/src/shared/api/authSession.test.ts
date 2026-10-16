import {
  clearAuthSession,
  onAuthSessionReset,
  setAuthSession,
} from "@/shared/api/authSession";
import { queryClient } from "@/shared/api/queryClient";
import { beforeEach, describe, expect, it } from "vitest";

describe("Auth Session & QueryClient Cache Isolation", () => {
  beforeEach(() => {
    clearAuthSession();
    queryClient.clear();
  });

  it("should remove every cached query when signing out", () => {
    setAuthSession({ access: "token-a", tenantId: "tenant-a" });
    queryClient.setQueryData(["profile"], { email: "a@example.com" });
    queryClient.setQueryData(["projects", "list"], [{ id: "project-of-a" }]);

    expect(queryClient.getQueryData(["profile"])).toEqual({
      email: "a@example.com",
    });

    clearAuthSession();

    expect(queryClient.getQueryData(["profile"])).toBeUndefined();
    expect(queryClient.getQueryData(["projects", "list"])).toBeUndefined();
    expect(queryClient.getQueryCache().getAll().length).toBe(0);
  });

  it("should keep cache on silent token refresh for the same tenant", () => {
    setAuthSession({ access: "token-b1", tenantId: "tenant-b" });
    queryClient.setQueryData(["profile"], { email: "b@example.com" });

    setAuthSession({ access: "token-b2", tenantId: "tenant-b" });
    setAuthSession({ access: "token-b3" });

    expect(queryClient.getQueryData(["profile"])).toEqual({
      email: "b@example.com",
    });
  });

  it("should drop cache when another tenant account takes over the session", () => {
    setAuthSession({ access: "token-b", tenantId: "tenant-b" });
    queryClient.setQueryData(["profile"], { email: "b@example.com" });

    setAuthSession({ access: "token-c", tenantId: "tenant-c" });

    expect(queryClient.getQueryData(["profile"])).toBeUndefined();
  });

  it("should prevent in-flight requests of previous user from repopulating the cache", async () => {
    let release!: (value: string) => void;
    const slowPromise = queryClient.fetchQuery({
      queryKey: ["slow-request"],
      queryFn: () =>
        new Promise<string>((resolve) => {
          release = resolve;
        }),
    });

    clearAuthSession();
    release("previous-user-data");

    await slowPromise.catch(() => undefined);
    expect(queryClient.getQueryData(["slow-request"])).toBeUndefined();
  });

  it("should correctly handle listener bookkeeping for session reset", () => {
    let calls = 0;
    const unsubscribe = onAuthSessionReset(() => {
      calls += 1;
    });

    clearAuthSession();
    unsubscribe();
    clearAuthSession();

    expect(calls).toBe(1);
  });
});

