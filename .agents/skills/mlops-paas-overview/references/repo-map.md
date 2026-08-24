# Repository map

| Path | Ownership |
| --- | --- |
| `web/` | React/Vite frontend and frontend quality gates |
| `services/control-plane/` | Django API, lifecycle orchestration, Celery, selectors and execution factories |
| `services/consumer/` | Redpanda inference-event ingestion and production-data persistence |
| `services/model-packager/` | Manual/training artifact packaging and image builds |
| `services/model-server/` | Authenticated inference gateway and event publication |
| `services/*-serving/` | ML and deep-learning worker runtimes |
| `services/evidently/` | Drift report execution |
| `services/training-runner/` | Untrusted training job runtime |
| `infra/` | Terraform AWS infrastructure |
| `ansible/` | VM/K3s, K3s token/TLS bootstrap, Argo CD bootstrap and verification |
| `k8s/` | Kustomize, GitOps applications, workflows, operators, and platform manifests |
| `.github/workflows/` | CI/CD orchestration |
| `docs/` | Supporting explanations; verify against live implementation |

## Control Plane domains

- `auth` and `access`: identity, OAuth, JWT/JWKS, API keys, authorization.
- `catalog`: model projects, workspace assets, deletion lifecycle.
- `registry`: versions, artifacts, metrics, insights, stages.
- `training`: jobs, snapshots, outputs, capabilities, cancellation.
- `deployment`: builds, deployments, endpoints, execution tasks.
- `drift`: monitor configuration, runs, production-data access, reports.
- `observability`: health, metrics, audit and runtime visibility.

## Source precedence

1. Executable code and current database migrations.
2. Tests that assert the current contract.
3. Kubernetes, Terraform, Ansible, Compose, and CI/CD configuration.
4. Focused documentation.
5. Root README, architecture summaries, and example environment files.

When sources conflict, document the discrepancy and follow the higher-authority source.
