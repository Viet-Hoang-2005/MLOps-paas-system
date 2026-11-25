import { test as base, expect } from "@playwright/test";
import {
  installMockApi,
  isLiveMode,
  type MockApiState,
} from "./mockApi";

interface E2EFixtures {
  mockApi: MockApiState;
}

export const test = base.extend<E2EFixtures>({
  mockApi: [
    async ({ page }, use) => {
      if (isLiveMode) {
        const dummyState = {
          authenticated: true,
          projects: [],
          builds: {},
          buildLogPollCount: {},
          listProjectsFailureCount: 0,
          runtimeLogsError: false,
        } satisfies MockApiState;
        await use(dummyState);
        return;
      }

      const state = await installMockApi(page, { authenticated: true });
      await use(state);
    },
    { auto: true },
  ],
});

export { expect, isLiveMode };
