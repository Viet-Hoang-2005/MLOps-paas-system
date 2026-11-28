import { listDriftMonitoringJobs } from "@/features/monitoring/api/driftApi";
import { useDriftMonitor } from "@/features/monitoring/hooks/useDriftMonitoring";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/shared/api/client", () => ({ apiClient: { get } }));

beforeEach(() => {
  get.mockReset();
});

it("shares monitor configuration and runs across subscribers", async () => {
  const monitor = { id: "monitor", runs: [{ id: "run" }] };
  get.mockResolvedValue({ data: monitor });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { result, unmount } = renderHook(
    () => [useDriftMonitor("monitor"), useDriftMonitor("monitor")] as const,
    {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    },
  );

  await waitFor(() => expect(result.current[1].data?.runs).toEqual(monitor.runs));
  expect(result.current[0].data).toEqual(monitor);
  expect(get).toHaveBeenCalledTimes(1);
  unmount();
  client.clear();
});

it("requests every monitor page with the same project filter", async () => {
  const first = { id: "first", project_id: "project" };
  const second = { id: "second", project_id: "project" };
  get
    .mockResolvedValueOnce({ data: { results: [first], next: "page-2" } })
    .mockResolvedValueOnce({ data: { results: [second], next: null } });

  expect(await listDriftMonitoringJobs("project")).toEqual([first, second]);
  const url = expect.stringMatching(/\/drift-monitors\/\?project_id=project$/);
  expect(get).toHaveBeenNthCalledWith(1, url, { params: { page: 1, page_size: 100 } });
  expect(get).toHaveBeenNthCalledWith(2, url, { params: { page: 2, page_size: 100 } });
});
