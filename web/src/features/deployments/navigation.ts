export function buildDeploymentPath(
  options: {
    projectId?: string;
    buildId?: string;
    source?: "preview" | "training";
    jobId?: string;
  } = {},
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(options)) {
    if (value) query.set(key, value);
  }
  return `/dashboard/deployment/build/new${query.size ? `?${query}` : ""}`;
}

export function runDeploymentPath(
  projectId: string,
  buildId: string,
  deploymentId?: string,
) {
  const path = `/dashboard/deployment/run/${encodeURIComponent(projectId)}/${encodeURIComponent(buildId)}`;
  return deploymentId
    ? `${path}?${new URLSearchParams({ deploymentId })}`
    : path;
}
