import type {
  ActiveModelEndpoint,
  ApiHealthStatus,
} from "@/features/projects/types";

export function currentApiHealth(
  endpoint: ActiveModelEndpoint | null | undefined,
  unavailable = false,
  now = Date.now(),
): ApiHealthStatus {
  if (unavailable || !endpoint || endpoint.deployment_status !== "succeeded")
    return "unknown";
  const checked = Date.parse(endpoint.last_checked_at ?? "");
  if (
    !Number.isFinite(checked) ||
    now - checked > 45000 ||
    checked > now + 5000
  )
    return "unknown";
  return endpoint.health_status;
}
