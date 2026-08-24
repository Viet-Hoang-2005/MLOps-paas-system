---
name: mlops-paas-backend
description: "Implement, diagnose, or review Python backend services and their contracts: Control Plane, consumer, model-packager, model-server, ML/DL serving, Evidently, and training-runner. Use for API, database, task, callback, execution, storage, inference, drift, or backend test changes."
---

# MLOps PaaS backend

## Workflow

1. Inspect the target service code, migrations, tests, Dockerfile, requirements, and calling/called services.
2. Read the service reference and [service-contracts.md](references/service-contracts.md). Read [control-plane.md](references/control-plane.md) for orchestrated lifecycle changes.
3. Keep validation/authorization, state mutation, transaction, async dispatch, execution, and callback boundaries explicit.
4. Mock databases, brokers, S3, Docker, MLflow, external HTTP, and Kubernetes in unit tests.
5. Preserve public API contracts unless the request explicitly changes them.
6. Resolve prose conflicts in favor of live code, migrations, tests, and manifests.
7. Preserve user changes; avoid unrelated refactors.
8. Update this skill when intentionally changing a backend contract.

Load `$mlops-paas-overview` for cross-service work, `$mlops-paas-environment` for backend selection, and `$mlops-paas-security` for tenant/auth/storage/callback/runtime changes.

Never embed passwords, tokens, private keys, real environment values, or SSH credentials in skills, tests, fixtures, or source.

## Identifier invariant

- Model packager: `BUILD_ID`.
- Serving and Evidently: `PROJECT_ID` plus `MODEL_VERSION_ID`.
- Training runner: `TRAINING_JOB_ID`.
- Never add a fallback for legacy `MODEL_ID`.

## Validation

Run the target service's isolated pytest suite with coverage as described in [testing.md](references/testing.md). For Control Plane changes, also run relevant Django checks/migration checks and focused app tests.
