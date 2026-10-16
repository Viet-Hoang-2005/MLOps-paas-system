import type { RuntimeMetricsResponse } from "@/features/overview/api/metricsApi";
import { createRealtimeSession } from "@/features/overview/realtimeMetrics";
import { describe, expect, it } from "vitest";

describe("Overview realtimeMetrics Session & Rate Calculation", () => {
  const snapshot = (
    timestamp: number,
    count: number,
    generation = "first",
    deployment_id = "deployment-1",
  ): RuntimeMetricsResponse => ({
    mode: "realtime",
    status: "available",
    deployment_id,
    snapshot: {
      timestamp,
      cpu: 0.2,
      memory: 64,
      request_counter: { count, generation },
    },
  });

  it("should calculate request rate delta and handle counter resets", () => {
    const collect = createRealtimeSession();

    // First snapshot has no previous counter to diff against
    expect(collect(snapshot(100, 5)).at(-1)?.requests).toBeNull();

    // 10 count delta over 5 seconds = 2 req/s
    expect(collect(snapshot(105, 15)).at(-1)?.requests).toBe(2);

    // 0 count delta over 5 seconds = 0 req/s
    expect(collect(snapshot(110, 15)).at(-1)?.requests).toBe(0);

    // Generation reset sets rate to null
    expect(collect(snapshot(115, 20, "reset")).at(-1)?.requests).toBeNull();
    expect(collect(snapshot(120, 1, "reset")).at(-1)?.requests).toBeNull();
  });

  it("should handle unavailable status and deployment switches", () => {
    const collect = createRealtimeSession();
    collect(snapshot(100, 5));

    const missing: RuntimeMetricsResponse = {
      mode: "realtime",
      status: "unavailable",
      deployment_id: "deployment-1",
      snapshot: null,
    };

    expect(collect(missing, 125).at(-1)?.cpu).toBeNull();

    // Switching deployment resets history
    expect(collect(snapshot(205, 10, "first", "deployment-2")).length).toBe(1);
  });

  it("should cap rolling window to 60 data points", () => {
    const capped = createRealtimeSession();
    let result: unknown[] = [];
    for (let i = 0; i < 100; i++) {
      result = capped(snapshot(i * 5, i));
    }
    expect(result.length).toBe(60);

    // A gap larger than MAX_AGE_SECONDS purges older points
    result = capped(snapshot(900, 100));
    expect(result.length).toBe(1);
  });
});

