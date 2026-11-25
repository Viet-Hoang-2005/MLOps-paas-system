import type { Page, Route } from "@playwright/test";

export const isLiveMode = Boolean(process.env.PLAYWRIGHT_BASE_URL?.trim());

export interface MockProject {
  id: string;
  name: string;
  description: string;
  access_mode: "private" | "public";
  is_active: boolean;
  deletion_state: "active" | "deleting" | "deleted" | "delete_failed";
  preview_revision: number;
  preview_changed: boolean;
  flavor: "sklearn" | "xgboost" | "pytorch" | "tensorflow" | "";
  lifecycle_status: "preview" | "registered" | "running";
  latest_version_id: string | null;
  latest_version_number: string | null;
  running_version_number: string | null;
  active_endpoint: {
    id: string;
    deployment_id: string;
    version_id: string;
    version_number: string;
    url: string;
    health_url: string;
    health_status: "healthy" | "unhealthy" | "unknown";
    deployment_status:
      | "pending"
      | "deploying"
      | "succeeded"
      | "failed"
      | "stopped"
      | "unconfirmed";
    registration_status:
      | "unregistered"
      | "registering"
      | "registered"
      | "failed";
    last_checked_at: string | null;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface MockBuild {
  id: string;
  project_id: string;
  version_id: string | null;
  version_number: string | null;
  source_job_id: string | null;
  preview_revision: number | null;
  flavor: string;
  artifact_format: "raw" | "mlflow_zip";
  requirements_snapshot: string;
  backend: "docker" | "argo";
  status: "pending" | "queued" | "building" | "ready" | "failed" | "cancelled";
  registration_status:
    | "unregistered"
    | "registering"
    | "registered"
    | "failed";
  registration_error: string;
  deletion_state: "active" | "deleting" | "delete_failed";
  deletion_error: string;
  image_uri: string;
  image_digest: string;
  package_uri: string;
  input_assets: Array<{ kind: string; name: string }>;
  logs: string;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface MockApiState {
  authenticated: boolean;
  projects: MockProject[];
  builds: Record<string, MockBuild>;
  buildLogPollCount: Record<string, number>;
  listProjectsFailureCount: number;
  runtimeLogsError: boolean;
  onBuildLogRequest?: (pollNumber: number, buildId: string) => {
    logs: string[];
    next_offset: number;
    status: string;
    error_message: string;
  };
}

export function createDefaultProjects(): MockProject[] {
  const now = new Date().toISOString();
  return [
    {
      id: "project-diabetes",
      name: "Diabetes-Logreg",
      description: "Logistic regression model for diabetes screening",
      access_mode: "private",
      is_active: true,
      deletion_state: "active",
      preview_revision: 1,
      preview_changed: false,
      flavor: "sklearn",
      lifecycle_status: "running",
      latest_version_id: "version-1",
      latest_version_number: "v1",
      running_version_number: "v1",
      active_endpoint: {
        id: "endpoint-1",
        deployment_id: "deploy-1",
        version_id: "version-1",
        version_number: "v1",
        url: "http://localhost:5002/models/project-diabetes/predict",
        health_url: "http://localhost:5002/models/project-diabetes/health",
        health_status: "healthy",
        deployment_status: "succeeded",
        registration_status: "registered",
        last_checked_at: now,
      },
      created_at: "2026-11-01T00:00:00Z",
      updated_at: now,
    },
    {
      id: "project-baf",
      name: "BAF-Fraud-Detector",
      description: "Tabular neural network for bank account fraud",
      access_mode: "public",
      is_active: true,
      deletion_state: "active",
      preview_revision: 1,
      preview_changed: true,
      flavor: "pytorch",
      lifecycle_status: "preview",
      latest_version_id: null,
      latest_version_number: null,
      running_version_number: null,
      active_endpoint: null,
      created_at: "2026-11-02T00:00:00Z",
      updated_at: now,
    },
  ];
}

export function createDefaultBuilds(): Record<string, MockBuild> {
  const now = new Date().toISOString();
  return {
    "build-1": {
      id: "build-1",
      project_id: "project-diabetes",
      version_id: "version-1",
      version_number: "1",
      source_job_id: null,
      preview_revision: 1,
      flavor: "sklearn",
      artifact_format: "raw",
      requirements_snapshot: "scikit-learn==1.6.1\nnumpy==2.0.2",
      backend: "docker",
      status: "building",
      registration_status: "unregistered",
      registration_error: "",
      deletion_state: "active",
      deletion_error: "",
      image_uri: "",
      image_digest: "",
      package_uri: "",
      input_assets: [{ kind: "source_artifact", name: "model.joblib" }],
      logs: "",
      error_message: "",
      created_at: now,
      updated_at: now,
    },
  };
}

function jsonResponse(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export async function installMockApi(
  page: Page,
  initial: Partial<MockApiState> = {},
): Promise<MockApiState> {
  const state: MockApiState = {
    authenticated: true,
    projects: createDefaultProjects(),
    builds: createDefaultBuilds(),
    buildLogPollCount: {},
    listProjectsFailureCount: 0,
    runtimeLogsError: false,
    ...initial,
  };

  await page.route(
    (url) => url.pathname.startsWith("/mock-s3/"),
    async (route) => {
      await route.fulfill({ status: 200, body: "" });
    },
  );

  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = request.method();

    if (path === "/auth/token/" && method === "POST") {
      const payload = request.postDataJSON() as {
        email?: string;
        password?: string;
      } | null;
      if (
        payload?.email === "developer@example.com" &&
        payload?.password === "Password123!"
      ) {
        state.authenticated = true;
        return jsonResponse(route, {
          access: "e2e-access-token",
          tenant_id: "tenant-default",
        });
      }
      return jsonResponse(
        route,
        { detail: "No active account found with the given credentials." },
        401,
      );
    }

    if (path === "/auth/token/refresh/" && method === "POST") {
      if (!state.authenticated) {
        return jsonResponse(
          route,
          { detail: "Token is invalid or expired" },
          401,
        );
      }
      return jsonResponse(route, {
        access: "e2e-access-token",
        tenant_id: "tenant-default",
      });
    }

    if (path === "/auth/logout/" && method === "POST") {
      state.authenticated = false;
      return jsonResponse(route, { message: "Signed out." });
    }

    if (path === "/auth/profile/" && method === "GET") {
      return jsonResponse(route, {
        id: "user-1",
        email: "developer@example.com",
        full_name: "Dev User",
        avatar: null,
        tenant_id: "tenant-default",
      });
    }

    if (path === "/notifications/" && method === "GET") {
      return jsonResponse(route, { results: [], count: 0, next: null });
    }

    if (path === "/notifications/unread-count/" && method === "GET") {
      return jsonResponse(route, { unread_count: 0 });
    }

    if (path === "/models/" && method === "GET") {
      if (state.listProjectsFailureCount > 0) {
        state.listProjectsFailureCount -= 1;
        return jsonResponse(
          route,
          { detail: "Temporary database outage" },
          500,
        );
      }
      return jsonResponse(route, { results: state.projects, next: null });
    }

    if (path === "/models/preview/upload-urls/" && method === "POST") {
      const payload = request.postDataJSON() as {
        files?: Array<{
          kind: string;
          filename: string;
          content_type?: string;
        }>;
      } | null;
      const origin = url.origin.replace(/\/api$/, "");
      return jsonResponse(route, {
        project_id: "project-created",
        files: (payload?.files ?? []).map((f) => ({
          kind: f.kind,
          filename: f.filename,
          s3_uri: `s3://mlops-paas-artifacts/preview/${f.filename}`,
          upload_url: `${origin}/mock-s3/${encodeURIComponent(f.filename)}`,
          content_type: f.content_type || "application/octet-stream",
        })),
      });
    }

    if (path === "/models/" && method === "POST") {
      const payload = request.postDataJSON() as {
        project_id?: string;
        name: string;
        description?: string;
        access_mode?: "private" | "public";
        flavor?: MockProject["flavor"];
      };
      const now = new Date().toISOString();
      const created: MockProject = {
        id: payload.project_id || `project-${state.projects.length + 1}`,
        name: payload.name,
        description: payload.description || "",
        access_mode: payload.access_mode || "private",
        is_active: true,
        deletion_state: "active",
        preview_revision: 1,
        preview_changed: false,
        flavor: payload.flavor || "sklearn",
        lifecycle_status: "preview",
        latest_version_id: null,
        latest_version_number: null,
        running_version_number: null,
        active_endpoint: null,
        created_at: now,
        updated_at: now,
      };
      state.projects.unshift(created);
      return jsonResponse(route, created, 201);
    }

    const modelDetailMatch = path.match(/^\/models\/([^/]+)\/$/);
    if (modelDetailMatch && method === "GET") {
      const project = state.projects.find((p) => p.id === modelDetailMatch[1]);
      if (!project) {
        return jsonResponse(route, { detail: "Not found" }, 404);
      }
      return jsonResponse(route, project);
    }

    const previewMatch = path.match(/^\/models\/([^/]+)\/preview\/$/);
    if (previewMatch && method === "GET") {
      const project = state.projects.find((p) => p.id === previewMatch[1]);
      return jsonResponse(route, {
        revision: project?.preview_revision ?? 1,
        flavor: project?.flavor || "sklearn",
        artifact_format: "raw",
        requirements_text: "scikit-learn==1.6.1\nnumpy==2.0.2",
        assets: [
          {
            kind: "source_artifact",
            name: "model.joblib",
            download_url: "",
          },
        ],
      });
    }

    if (/^\/models\/[^/]+\/running-attributes\/$/.test(path)) {
      return jsonResponse(route, {
        metrics: { accuracy: 0.91 },
        params: { max_iter: 1000 },
        insights: {},
        feature_importance: [],
        input_schema: null,
      });
    }

    const modelBuildsMatch = path.match(/^\/models\/([^/]+)\/builds\/$/);
    if (modelBuildsMatch && method === "GET") {
      const matching = Object.values(state.builds).filter(
        (b) => b.project_id === modelBuildsMatch[1],
      );
      return jsonResponse(route, matching);
    }

    const buildDetailMatch = path.match(/^\/builds\/([^/]+)\/$/);
    if (buildDetailMatch && method === "GET") {
      const build = state.builds[buildDetailMatch[1]];
      if (!build) {
        return jsonResponse(route, { detail: "Not found" }, 404);
      }
      return jsonResponse(route, build);
    }

    const buildLogsMatch = path.match(/^\/builds\/([^/]+)\/logs\/$/);
    if (buildLogsMatch && method === "GET") {
      const buildId = buildLogsMatch[1];
      const count = (state.buildLogPollCount[buildId] ?? 0) + 1;
      state.buildLogPollCount[buildId] = count;
      if (state.onBuildLogRequest) {
        return jsonResponse(route, state.onBuildLogRequest(count, buildId));
      }
      return jsonResponse(route, {
        logs: ["Starting BUILD process", "Build completed."],
        next_offset: 2,
        status: "ready",
        error_message: "",
      });
    }

    const runtimeLogsMatch = path.match(
      /^\/deployments\/([^/]+)\/runtime-logs\/$/,
    );
    if (runtimeLogsMatch && method === "GET") {
      if (state.runtimeLogsError) {
        return jsonResponse(route, {
          logs: [],
          next_offset: 0,
          status: "succeeded",
          error_message: "",
          log_error: "unavailable",
        });
      }
      return jsonResponse(route, {
        logs: [
          "2026-11-24T10:00:00Z [INFO]: Uvicorn running on http://0.0.0.0:5001",
          "2026-11-24T10:00:01Z [INFO]: Model artifact loaded",
        ],
        next_offset: 2,
        status: "succeeded",
        error_message: "",
      });
    }

    if (path === "/deployments/" && method === "GET") {
      return jsonResponse(route, { results: [], next: null });
    }

    if (/^\/registry\/models\/[^/]+\/versions\/$/.test(path)) {
      return jsonResponse(route, []);
    }

    if (path === "/registry/versions/version-1/" && method === "GET") {
      return jsonResponse(route, {
        id: "version-1",
        project_id: "project-diabetes",
        version: "1",
        source_job_id: null,
        requirements_snapshot: "scikit-learn==1.6.1",
        flavor: "sklearn",
        stage: "production",
        deployability: "deployable",
        deployability_reason: "",
        metrics_summary: { accuracy: 0.91 },
        params_summary: { max_iter: 1000 },
        insights_summary: {},
        artifacts: [],
        metrics: [],
        events: [],
        registered_at: "2026-11-01T01:00:00Z",
      });
    }

    if (path === "/training/workspaces/" && method === "GET") {
      return jsonResponse(route, { workspaces: [] });
    }

    if (path === "/training-jobs/" && method === "GET") {
      return jsonResponse(route, { training_jobs: [] });
    }

    if (path === "/training-jobs/capabilities/" && method === "GET") {
      return jsonResponse(route, {
        gpu_enabled: false,
        gpu_models: [],
        flavors: ["sklearn", "xgboost", "pytorch", "tensorflow"],
      });
    }

    if (path === "/training-jobs/usage/" && method === "GET") {
      return jsonResponse(route, { buckets: [] });
    }

    if (path === "/drift-monitors/" && method === "GET") {
      return jsonResponse(route, { results: [], next: null });
    }

    if (path === "/api-keys/" && method === "GET") {
      return jsonResponse(route, { results: [] });
    }

    return jsonResponse(route, {});
  });

  return state;
}
