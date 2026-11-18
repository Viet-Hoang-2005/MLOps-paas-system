---
name: mlops-paas-environment
description: Diagnose environment-specific behavior and change runtime configuration for Docker Compose or production K3s, including connectivity, settings, and worker restarts.
---

# MLOps PaaS Environment

Identify the process that fails and its selected settings and execution backend. Verify service DNS, ports and configuration from that process's network. Distinguish a stale image or process from a source-code failure before changing configuration.

- Local topology, service profiles and dependency startup: [Docker Compose](references/local-docker-compose.md).
- Production settings, overlays, ExternalSecrets and runtime ownership: [Production runtime](references/production-runtime.md).
- Where to check defaults and overrides: [Configuration matrix](references/configuration-matrix.md).
- Symptom triage and safe restart checks: [Troubleshooting](references/troubleshooting.md).

For Python image dependencies, read the target service Dockerfile and the requirements it installs. The service images use Python 3.12. Verify changes in the target Docker environment rather than relying on a host-only install. Use the [backend testing reference](../mlops-paas-backend/references/testing.md) for the dependency and service checks.
