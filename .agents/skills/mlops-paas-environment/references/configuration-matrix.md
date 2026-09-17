# Configuration matrix

| Category | Local | Production |
| --- | --- | --- |
| Execution | Docker SDK/Compose network | Argo/Kubeflow/Kubernetes |
| Images | Docker image store | Harbor registry |
| Artifacts | S3-compatible configuration/AWS S3 | AWS S3 |
| Secrets | developer `.env` | Secrets Manager + External Secrets |
| Public routing | localhost + Traefik | ingress/tunnel/load-balancer design |
| Runtime naming | Docker container names | Kubernetes resource names |

## Precedence

1. Component-specific backend setting.
2. Global `EXECUTION_BACKEND`.
3. Code default.

Confirm actual setting names in Control Plane settings and ConfigMaps before changing them.

## Variable groups

- Database, Redis, broker, MLflow.
- S3 region/bucket/endpoints and presign TTL.
- OAuth/JWT/API/security secrets.
- Docker/registry/Harbor.
- Argo Events/Workflow namespaces and service endpoints.
- Runtime IDs and scoped callback/upload URLs.

Never copy real values into skills or source. Do not assume example values are current contracts.

## Backend logging

Each application owns its logging utilities (`src/logging_utils.py`, or
`src/common/logging_utils.py` for Control Plane). Docker build context is
`services/<service>` with its own `.dockerignore`; no shared logging installation.
Set `LOG_FORMAT=console` (the default) for readable container output, or
`LOG_FORMAT=json` before reproducing an incident to retain structured metadata.
Compose selects `Dockerfile` within that context; CI/CD use `matrix.target.context`
and the explicit repository-relative Dockerfile path. Per-service path changes
select only that service. Gateway/ML-serving use `src.uvicorn_entrypoint`; Django,
Celery/Gunicorn and BentoML retain their local adapters. MLflow keeps its own context. Default `LOG_LEVEL=INFO` and
`LOG_SUMMARY_INTERVAL_SECONDS=60` apply to Compose and production execution.
Production training has no shared Redis log credentials: retain sanitized container
detail until a trusted job-log transport exists. Do not remove that fallback.
