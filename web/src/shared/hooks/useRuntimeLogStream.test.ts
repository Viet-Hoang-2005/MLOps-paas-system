import * as runtimeLogsApi from "@/shared/api/runtimeLogs";
import { useRuntimeLogStream } from "@/shared/hooks/useRuntimeLogStream";
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("useRuntimeLogStream Hook", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("should initialize with empty logs and idle status when disabled or no source", () => {
    const { result } = renderHook(() =>
      useRuntimeLogStream({ source: null, enabled: false }),
    );

    expect(result.current.logs).toEqual([]);
    expect(result.current.status).toBeNull();
    expect(result.current.isPolling).toBe(false);
  });

  it("should poll logs and accumulate batches incrementally", async () => {
    const mockLogs = vi
      .spyOn(runtimeLogsApi, "getRuntimeLogs")
      .mockResolvedValueOnce({
        logs: ["line 1", "line 2"],
        nextOffset: 2,
        nextCursor: "c1",
        status: "running",
        hasMore: true,
        error: "",
        logError: undefined,
      })
      .mockResolvedValueOnce({
        logs: ["line 3"],
        nextOffset: 3,
        nextCursor: "c2",
        status: "succeeded",
        hasMore: false,
        error: "",
        logError: undefined,
      });

    vi.useFakeTimers();

    const { result } = renderHook(() =>
      useRuntimeLogStream({
        source: { kind: "training", id: "job-1" },
        enabled: true,
        terminalStatuses: ["succeeded", "failed"],
        pollIntervalMs: 500,
      }),
    );

    // Let initial poll execute
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    expect(mockLogs).toHaveBeenCalledTimes(1);
    expect(result.current.logs).toEqual(["line 1", "line 2"]);
    expect(result.current.status).toBe("running");

    // Second poll after interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(mockLogs).toHaveBeenCalledTimes(2);
    expect(result.current.logs).toEqual(["line 1", "line 2", "line 3"]);
    expect(result.current.status).toBe("succeeded");

    vi.useRealTimers();
  });
});
