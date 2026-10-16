import { currentApiHealth } from "@/features/overview/runtimeHealth";
import type { ActiveModelEndpoint } from "@/features/projects/types";
import { describe, expect, it } from "vitest";

describe("Overview runtimeHealth - Health Status Expiry & State Evaluation", () => {
  const now = Date.now();
  const endpoint = {
    version_id: "v1",
    deployment_status: "succeeded",
    health_status: "healthy",
    last_checked_at: new Date(now).toISOString(),
  } as unknown as ActiveModelEndpoint;

  it("should return healthy status when checked recently", () => {
    expect(currentApiHealth(endpoint, false, now)).toBe("healthy");
    expect(
      currentApiHealth({ ...endpoint, health_status: "unhealthy" }, false, now),
    ).toBe("unhealthy");
    expect(
      currentApiHealth({ ...endpoint, health_status: "unknown" }, false, now),
    ).toBe("unknown");
  });

  it("should evaluate status as unknown when unavailable or expired", () => {
    expect(currentApiHealth(endpoint, true, now)).toBe("unknown");
    // Expired after 45s threshold
    expect(currentApiHealth(endpoint, false, now + 46000)).toBe("unknown");
    expect(currentApiHealth({ ...endpoint, last_checked_at: null }, false, now)).toBe(
      "unknown",
    );
    expect(
      currentApiHealth({ ...endpoint, last_checked_at: "invalid-date" }, false, now),
    ).toBe("unknown");
    // Timestamp from the future (> 5s clock skew)
    expect(
      currentApiHealth(
        { ...endpoint, last_checked_at: new Date(now + 6000).toISOString() },
        false,
        now,
      ),
    ).toBe("unknown");
  });

  it("should return unknown when deployment is not succeeded or endpoint is null", () => {
    expect(
      currentApiHealth({ ...endpoint, deployment_status: "stopped" }, false, now),
    ).toBe("unknown");
    expect(currentApiHealth(null, false, now)).toBe("unknown");
  });
});
