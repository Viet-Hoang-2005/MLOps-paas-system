import type { RuntimeMetricsResponse } from "@/features/projects/api/metricsApi";

export type MetricKey = "cpu" | "memory" | "requests";
export interface RealtimePoint {
  timestamp: number;
  cpu: number | null;
  memory: number | null;
  requests: number | null;
}

const MAX_POINTS = 60;
const MAX_AGE_SECONDS = 300;
const MAX_RATE_GAP_SECONDS = 15;
const finite = (value: number | null | undefined) =>
  typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;

// Per mounted query observer: no browser storage, timer, or persisted history.
export function createRealtimeSession(initialDeploymentId: string | null = null) {
  let deploymentId: string | null = initialDeploymentId;
  let points: RealtimePoint[] = [];
  let previous: RuntimeMetricsResponse["snapshot"] = null;
  return (response: RuntimeMetricsResponse, now = Date.now() / 1000) => {
    if (response.deployment_id !== deploymentId) {
      deploymentId = response.deployment_id;
      points = [];
      previous = null;
    }
    if (response.mode !== "realtime") return [];
    const sample = response.snapshot;
    const timestamp = sample?.timestamp ?? now;
    if (points.length && timestamp <= points[points.length - 1].timestamp)
      return points;
    let rate: number | null = null;
    const counter = sample?.request_counter;
    const lastCounter = previous?.request_counter;
    const interval =
      previous && sample ? sample.timestamp - previous.timestamp : 0;
    if (
      counter &&
      lastCounter &&
      counter.generation === lastCounter.generation &&
      interval > 0 &&
      interval <= MAX_RATE_GAP_SECONDS &&
      counter.count >= lastCounter.count
    ) {
      rate = finite((counter.count - lastCounter.count) / interval);
    }
    points = [
      ...points.filter(
        (point) => timestamp - point.timestamp <= MAX_AGE_SECONDS,
      ),
      {
        timestamp,
        cpu: finite(sample?.cpu),
        memory: finite(sample?.memory),
        requests: rate,
      },
    ].slice(-MAX_POINTS);
    previous = sample ?? null;
    return points;
  };
}
