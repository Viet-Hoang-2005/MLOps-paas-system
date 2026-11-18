# Working in MLOps PaaS

1. Find the entry point for the reported behavior and the caller that reaches it.
2. Trace data and state across the relevant boundaries for the selected environment.
3. Change the component that owns the behavior and preserve the contracts its callers use.
4. Run the smallest relevant checks, then any affected CI gates. Report which checks ran and where.

Start with [MLOps PaaS Overview](.agents/skills/mlops-paas-overview/SKILL.md) for a cross-service change or when ownership is unclear. Otherwise use the closest domain skill. Read its references as the task requires.

| Area | Skill |
| --- | --- |
| React routes, queries, shared UI and i18n | [Frontend](.agents/skills/mlops-paas-frontend/SKILL.md) |
| Python services, API contracts and async jobs | [Backend](.agents/skills/mlops-paas-backend/SKILL.md) |
| Docker Compose, settings and runtime diagnosis | [Environment](.agents/skills/mlops-paas-environment/SKILL.md) |
| Terraform, Ansible and K3s bootstrap | [Infrastructure](.agents/skills/mlops-paas-architecture/SKILL.md) |
| GitOps, Argo execution, image promotion and cluster workloads | [Deployment](.agents/skills/mlops-paas-deployment/SKILL.md) |
| Tenancy, credentials, capabilities, IAM and untrusted workloads | [Security](.agents/skills/mlops-paas-security/SKILL.md) |

Use the executable entry points, tests and selected configuration to confirm behavior. [README](README.md), [architecture](ARCHITECTURE.md) and [testing](TESTING.md) give context. [CI](.github/workflows/ci.yml) defines the current merge checks. Keep credentials and signed URLs out of patches, examples and outputs. Treat production reads and mutations as separate from local validation and confirm that the requested scope covers them.
