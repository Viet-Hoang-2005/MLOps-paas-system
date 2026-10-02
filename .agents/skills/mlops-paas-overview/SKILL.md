---
name: mlops-paas-overview
description: Orient cross-cutting work in the MLOps PaaS repository, including component ownership, system planes, identifiers, state ownership, and upload, training, deployment, inference, and drift lifecycles. Use before work that spans multiple services or when the correct domain skill is unclear.
---

# MLOps PaaS Overview

Use this skill to establish system context and understand cross-cutting boundaries before modifying contracts, services, or configurations.

Never embed passwords, tokens, private keys, real environment values, or SSH credentials in skills, tests, or source code.

## Workflow

1. Inspect the live files involved in the request. Treat code, migrations, tests, manifests, and workflows as authoritative.
2. Read [repo-map.md](references/repo-map.md) to identify component ownership across the 10 Control Plane apps, 7 application services, and infrastructure layers.
3. Read [system-architecture.md](references/system-architecture.md) for state, plane, and execution boundaries.
4. Read the applicable lifecycle in [lifecycles.md](references/lifecycles.md) (Training, Packaging & Build, Serving & Inference, Drift & Continuous Training).
5. Read [cross-service-contracts.md](references/cross-service-contracts.md) before changing IDs, storage paths, callbacks, images, or routing.
6. Load every affected domain skill. Always load `$mlops-paas-security` when modifying tenancy, credentials, webhooks, IAM, untrusted workloads, or public exposure.
7. Reconcile stale READMEs, `.env.example`, or documentation prose with live implementation rather than blindly copying it.
8. Preserve user changes and avoid unrelated refactors.

## Domain Routing

- Web UI, routing, state, design tokens, or i18n: `$mlops-paas-frontend`
- Python services or API contracts (Control Plane, Consumer, Model Server, Serving workers, Packager, Runner, Evidently): `$mlops-paas-backend`
- Docker Compose, environment configuration, or local-versus-production parity: `$mlops-paas-environment`
- Terraform, AWS IaaS, Ansible, or K3s cluster bootstrap: `$mlops-paas-architecture`
- K3s GitOps resources, Kustomize overlays, Argo CD/Workflows, Kubeflow, or platform operations: `$mlops-paas-deployment`
- Any security-sensitive change (auth, capabilities, presigned URLs, untrusted workloads, secrets): `$mlops-paas-security`

## Invariants

- **State Ownership:** PostgreSQL (`schema control_plane`) and AWS S3 are the sources of truth. Redis is strictly a transient queue (Celery broker), result backend, and real-time runtime log stream.
- **Identifier Invariant:** Public resources exclusively use UUIDs; integer database primary keys remain strictly internal.
  - Model Packager: `BUILD_ID`
  - Training Runner: `TRAINING_JOB_ID`
  - Serving & Evidently: Pair of `PROJECT_ID` and `MODEL_VERSION_ID`
  - Drift Execution: `DRIFT_RUN_ID`
  - Never reintroduce the legacy `MODEL_ID` variable.
- **Strict Layering:** API endpoints must never directly interact with Docker, S3, Argo, Harbor, or Redis. Operations must route through domain services/selectors and dispatch via Celery at `transaction.on_commit`.
- **Idempotent Callbacks:** All internal callbacks must validate the reporter secret, accept `Idempotency-Key`, and use `select_for_update()`. Late callbacks must never resurrect cancelled or deleting resources.
- **Untrusted Workloads:** Training code is untrusted tenant code. Containers execute in a sandbox without AWS credentials, database passwords, or cluster admin access; they operate solely via short-lived Capability Tokens and Presigned S3 URLs.

## Validation

Run the smallest affected domain test suites:
- Kubernetes & GitOps manifests: `pytest k8s/validate/tests/`
- Service-specific tests: `python -m pytest` within the target service directory (e.g. `services/control-plane`, `services/consumer`, `services/model-server`).
- Run `git diff --check` to verify code formatting and prevent whitespace anomalies.
