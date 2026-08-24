---
name: mlops-paas-environment
description: Configure or troubleshoot local Docker Compose and production runtime differences, including service topology, ports, volumes, execution backends, environment variables, secrets, container restarts, and Docker-versus-Argo behavior. Use for environment-specific failures or configuration changes.
---

# MLOps PaaS environment

## Workflow

1. Determine whether the request targets local Docker Compose, production K3s, or both.
2. Inspect Compose/manifests/settings and the affected service before assuming defaults.
3. Read [configuration-matrix.md](references/configuration-matrix.md), then the matching runtime reference.
4. Keep secrets out of commands, logs, patches, and answers.
5. Use read-only health/log inspection before restarts or mutations.
6. Reconcile `.env.example` with live code; it may contain stale examples.
7. Preserve user changes and update this skill when environment behavior intentionally changes.

Load `$mlops-paas-backend` for service behavior, `$mlops-paas-deployment` for K3s resources, and `$mlops-paas-security` for credentials or exposure.

For cross-service environment changes also load `$mlops-paas-overview`. Treat code, tests, Compose, settings, and manifests as more authoritative than README or architecture prose; reconcile conflicts explicitly.

## Validation

Use `docker compose config` locally. In production, render Kustomize and use server-side/client dry-run where access permits. Restart only the affected component and verify health/logs afterward.
