export function createMockProject(overrides: Record<string, unknown> = {}) {
  return {
    id: "project-1",
    name: "Customer Churn Prediction",
    description: "ML project for churn detection",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    active_endpoint: {
      version_id: "version-1",
      deployment_status: "succeeded",
      health_status: "healthy",
      last_checked_at: new Date().toISOString(),
    },
    ...overrides,
  };
}

export function createMockModelVersion(
  id = "version-1",
  time = "2026-01-01T00:00:00Z",
  overrides: Record<string, unknown> = {},
) {
  return {
    id,
    project_id: "project-1",
    version: id,
    registered_at: time,
    source_job_id: null,
    flavor: "xgboost",
    requirements_snapshot: "numpy>=1.24\npandas>=2.0",
    deployability: "deployable",
    deployability_reason: "",
    stage: "none",
    artifacts: [],
    metrics: [],
    events: [],
    metrics_summary: { accuracy: 0.92, f1: 0.89 },
    params_summary: { max_depth: 6, n_estimators: 100 },
    insights_summary: {},
    ...overrides,
  };
}

export function createMockBuild(overrides: Record<string, unknown> = {}) {
  return {
    id: "build-1",
    project_id: "project-1",
    version_id: "version-1",
    status: "ready",
    registration_status: "registered",
    deletion_state: "active",
    image_uri: "registry.example.com/mlops/churn:v1",
    created_at: "2026-01-01T01:00:00Z",
    ...overrides,
  };
}

export function createMockDeployment(overrides: Record<string, unknown> = {}) {
  return {
    id: "deployment-1",
    build_id: "build-1",
    project_id: "project-1",
    version_id: "version-1",
    status: "succeeded",
    health_status: "healthy",
    endpoint_url: "https://api.example.com/predict",
    created_at: "2026-01-01T02:00:00Z",
    ...overrides,
  };
}

