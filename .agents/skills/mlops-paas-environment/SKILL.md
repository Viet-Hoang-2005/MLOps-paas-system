---
name: mlops-paas-environment
description: Configure or troubleshoot local Docker Compose and production runtime differences, including service topology, ports, volumes, execution backends, environment variables, secrets, container restarts, and Docker-versus-Argo behavior. Use for environment-specific failures or configuration changes.
---

# MLOps PaaS Environment

Use this skill to configure, diagnose, or troubleshoot differences between the local Docker Compose development environment and the production Kubernetes K3s runtime.

Never embed passwords, tokens, private keys, real environment values, or SSH credentials in skills, code, or answers.

## Workflow

1. Determine whether the request targets local Docker Compose, production K3s, or environment parity.
2. Read [configuration-matrix.md](references/configuration-matrix.md) and [local-docker-compose.md](references/local-docker-compose.md) or [production-runtime.md](references/production-runtime.md).
3. Inspect `docker-compose.yml`, `.env.example`, and K3s ConfigMaps/ExternalSecrets before assuming defaults.
4. Keep secrets strictly out of shell commands, logs, and commit history.
5. Reconcile `.env.example` with live code; treat application settings modules (`services/control-plane/src/config/settings/`) as authoritative.
6. Verify read-only health endpoints (`/health/live`, `/health/ready`) before and after configuration changes.

## Environment Differences

| Dimension | Local Docker Compose | Production Kubernetes K3s |
|---|---|---|
| **Execution Engine** | `EXECUTION_BACKEND=docker` (Docker SDK) | `EXECUTION_BACKEND=argo` (Argo Events/Workflows + Kubeflow) |
| **Image Registry** | Local Docker daemon cache | Harbor OCI Registry (`user-images/*`) |
| **Database** | Single PostgreSQL container | CloudNativePG High-Availability cluster |
| **Redis** | `REDIS_CONNECTION_MODE=direct` | `REDIS_CONNECTION_MODE=sentinel` (3 Sentinels + Master) |
| **Runtime Logs** | `LOG_STORAGE_BACKEND=redis` (Redis Streams) | `LOG_STORAGE_BACKEND=loki` (Grafana Loki + Signed Proxy) |
| **Secrets Delivery** | `.env` file | AWS Secrets Manager + External Secrets Operator |
| **AWS Infra Mode** | S3-only (`s3-only.tfvars`) | Full production infrastructure (`terraform.tfvars`) |

## Validation

- **Local:** Validate Compose syntax with `docker compose config`.
- **Production:** Validate Kustomize rendering with `kubectl kustomize k8s/apps/overlays/production`.
- Verify health endpoints after container or pod restarts:
  ```bash
  curl http://localhost:8000/health/ready # Control Plane
  curl http://localhost:5002/             # Model Server Gateway
  ```
