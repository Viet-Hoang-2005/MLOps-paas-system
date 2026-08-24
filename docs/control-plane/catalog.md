# Control Plane API Catalog

All public resource identifiers are UUIDs. Routes have no `/v1` prefix and no
legacy aliases.

## Public API

| Area | Routes |
|---|---|
| Identity | `/api/auth/token/`, `/api/auth/token/refresh/`, `/api/auth/register/`, `/api/auth/profile/`, OTP, password, OAuth, JWKS routes |
| API keys | `/api/api-keys/`, `/api/api-keys/{key_uuid}/`, `/api/api-keys/{key_uuid}/regenerate/` |
| Projects | `/api/models/`, `/api/models/{project_uuid}/`, `/api/models/{project_uuid}/builds/`, `/api/models/{project_uuid}/production-data/?limit={n}` |
| Workspace | `/api/models/{project_uuid}/workspace/{code|data}/files/` |
| Versions | `/api/registry/models/{project_uuid}/versions/`, `/api/registry/versions/{version_uuid}/`, `/{version_uuid}/smoke-test/` |
| Aliases | `/api/registry/models/{project_uuid}/aliases/`, `/api/registry/models/{project_uuid}/aliases/{alias}/predict/` |
| Training | `/api/training-jobs/`, `/{job_uuid}/`, `/{job_uuid}/submit/`, `/{job_uuid}/cancel/`, `/{job_uuid}/events/`, `/{job_uuid}/download/` |
| Builds | `/api/models/{project_uuid}/builds/` (manual multipart create/list), `/api/builds/`, `/api/builds/{build_uuid}/`, `/api/builds/{build_uuid}/logs/?offset={n}`, `/api/builds/{build_uuid}/cancel/` |
| Deployments | `/api/deployments/`, `/{deployment_uuid}/`, `/{deployment_uuid}/logs/?offset={n}`, `/{deployment_uuid}/stop/` |
| Endpoints | `/api/endpoints/`, `/api/endpoints/{endpoint_uuid}/logs/` |
| Drift | `/api/drift-monitors/`, `/{monitor_uuid}/`, `/{monitor_uuid}/runs/`, `/api/drift-monitors/runs/{run_uuid}/logs/?offset={n}` |
| Observability | `/api/observability/models/{project_uuid}/` |
| Operations | `/health/live`, `/health/ready`, `/health/metrics` |

Collections use the shared DRF pagination envelope. Input serializers validate
tenant ownership before services mutate state. API key secrets are returned only
on creation or regeneration and can be scoped only to projects owned by the user.

Production data is private to the project owner. The production-data route validates
the authenticated user's ownership before reading `public.paas_production_logs`, filters
by both tenant and project UUID, returns all matching rows when `limit` is omitted, and
requires a positive integer when `limit` is provided.

Project `name`, `description`, `access_mode`, source code, and reference data are latest-only metadata. Manual Build input belongs to one Build UUID and is snapshotted before execution. The build image is created as `image-{project_uuid}:build-{build_uuid}` locally or under Harbor project `user-images` in production. A successful callback atomically allocates the next model version, retags the same manifest as `v{version_number}`, records its Docker image ID or OCI manifest digest, copies the artifact snapshot to the version prefix, and marks the Build ready. Deployment pins that immutable identity rather than resolving a mutable tag. Callback replay is idempotent; failed/cancelled Builds do not allocate a version.

## Inference URL

Public endpoint URLs use:

```text
/{tenant_id}/models/{project_uuid}/{version_uuid}/predict
/{tenant_id}/models/{project_uuid}/{version_uuid}/health
```

Traefik rewrites these paths to the central model server as
`/models/{version_uuid}/{action}`. The model server resolves the healthy endpoint
from the control-plane schema and enforces project access mode/API key scope.
