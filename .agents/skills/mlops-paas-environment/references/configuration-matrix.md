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
