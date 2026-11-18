---
name: mlops-paas-overview
description: Trace cross-service behavior and locate its owner in MLOps PaaS. Use for architecture orientation, changes spanning system boundaries, or unclear ownership.
---

# MLOps PaaS Overview

Start with the user-visible entry point or failing stage and identify the selected execution backend. Use the [repo map](references/repo-map.md) to find the owner, then follow the routing table in [AGENTS.md](../../../AGENTS.md) for the domains touched.

- [System architecture](references/system-architecture.md) maps the control, execution, serving and observability boundaries. PostgreSQL owns lifecycle state and production records, S3 stores payloads, Harbor stores images, and Redis handles transient coordination and caching.
- [Core lifecycles](references/lifecycles.md) traces Training, Build/Deploy and Predict/Drift. Read the one whose entry point or behavior changes.
- [Cross-service contracts](references/cross-service-contracts.md) points to the owners of public UUIDs, storage keys, callbacks and telemetry. Check both ends before editing a shared contract.

Find the exact config used by the caller before relying on a documented default. A local Docker result and a rendered K3s manifest answer different questions.
