# Configuration Matrix

## Environment Comparison Matrix

| Category | Local Docker Compose | Production Kubernetes K3s |
|---|---|---|
| **Execution Backend** | `EXECUTION_BACKEND=docker` | `EXECUTION_BACKEND=argo` |
| **Component Overrides** | `BUILD_BACKEND=docker`<br>`DEPLOYMENT_BACKEND=docker`<br>`TRAINING_BACKEND=docker`<br>`DRIFT_BACKEND=docker` | Can be set to `argo` or `docker` independently |
| **Container Images** | Local Docker daemon cache | Harbor OCI Registry (`user-images/*`) |
| **Relational Database** | Single PostgreSQL container (`mlops_paas_db`) | CloudNativePG HA Cluster (`schema control_plane`) |
| **Redis Connection** | `REDIS_CONNECTION_MODE=direct` (`redis://:$REDIS_PASSWORD@redis:6379/1`, password required) | `REDIS_CONNECTION_MODE=sentinel` (`REDIS_SENTINEL_HOSTS`, `REDIS_SENTINEL_MASTER_NAME`) |
| **Log Storage** | `LOG_STORAGE_BACKEND=redis` (Redis streams: `*_logs:*`) | `LOG_STORAGE_BACKEND=loki` (Grafana Loki with task-bound cursors) |
| **Message Broker** | Single Redpanda container (`redpanda:9092`) | Redpanda Operator HA cluster (`mlops_paas_production_data`) |
| **Storage S3** | AWS S3 (`s3-only.tfvars`) or local S3-compatible | AWS S3 (`mlops-paas-artifacts` & `mlops-paas-runtime-logs`) |
| **Secrets Delivery** | Local `.env` file | AWS Secrets Manager synchronized by External Secrets Operator (ESO) |
| **Public Routing** | Direct ports (`8000`, `5001`, `5002`, `5004`, `5173`) | AWS ALB + Traefik Ingress Controller + Cloudflare Tunnel |

## Setting Precedence

1. Component-specific execution override (`BUILD_BACKEND`, `TRAINING_BACKEND`, etc.).
2. Global `EXECUTION_BACKEND`.
3. Code default (`docker`).

## Logging Configurations

- `LOG_FORMAT`: `console` (human-readable single line, default) or `json` (one-line structured JSON).
- `LOG_LEVEL`: Default `INFO`.
- `LOG_SUMMARY_INTERVAL_SECONDS`: Default `60` (summarizes high-frequency metrics per process every 60s).
