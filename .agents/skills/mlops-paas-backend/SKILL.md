---
name: mlops-paas-backend
description: Implement, diagnose, or review Python backend services and their contracts: Control Plane, consumer, model-packager, model-server, ML/DL serving, Evidently, and training-runner. Use for API, database, task, callback, execution, storage, inference, drift, or backend test changes.
---

# MLOps PaaS Backend

Use this skill to implement, modify, review, or troubleshoot Python backend services, API endpoints, database interactions, Celery tasks, and execution runners.

Never embed passwords, tokens, private keys, real environment values, or SSH credentials in skills, tests, fixtures, or source code.

## Workflow

1. Inspect target service code, migrations, tests, Dockerfile, requirements, and calling/called services.
2. Read the specific service reference (e.g. [control-plane.md](references/control-plane.md), [consumer.md](references/consumer.md), [model-server.md](references/model-server.md)) and [service-contracts.md](references/service-contracts.md).
3. Maintain explicit boundaries between API serializers, tenant-scoped selectors, transaction services, async Celery tasks, and execution backends.
4. Mock databases, message brokers, S3, Docker, MLflow, HTTP clients, and Kubernetes in unit tests.
5. Preserve public API contracts, response schemas, and error semantics unless explicitly requested to change them.
6. Resolve prose conflicts in favor of live source code, migrations, tests, and Kubernetes manifests.
7. Preserve user modifications and avoid unrelated refactors.
8. When intentionally altering a backend service contract, update this skill and its references.

## Architectural Boundaries

- **Strict Layering:** API endpoints must never directly invoke external infrastructure clients (Docker, Boto3, Argo, Harbor, Redis).
- **Transactional Dispatch:** Celery tasks must be dispatched inside `transaction.on_commit` hooks, ensuring the database transaction has committed before the background task runs.
- **Service Segregation:**
  - `control-plane`: 10 domain apps (`auth`, `access`, `catalog`, `registry`, `training`, `deployment`, `drift`, `ct`, `production`, `observability`).
  - `consumer`: Redpanda Kafka ingestion, micro-batching into PostgreSQL, and Transactional Outbox for drift signals.
  - `model-server`: Trusted inference gateway, RS256 JWT / JWKS auth, project API keys, dynamic worker routing, and asynchronous Kafka telemetry emission.
  - `machine-learning-serving`: Stateless FastAPI worker for Scikit-Learn/XGBoost, Model Signature column ordering, and confidence calculation via `predict_proba`.
  - `deep-learning-serving`: Stateless BentoML worker for PyTorch/TensorFlow, MLflow PyFunc loading, and tensor normalization.
  - `model-packager`: Formats models to MLflow PyFunc, generates Dockerfiles, and builds images via Docker SDK (local) or Kaniko (production).
  - `training-runner`: Untrusted training execution sandbox, short-lived Capability Tokens, Presigned S3 URLs, process group termination on `SIGTERM`, and `METRIC_JSON` log parsing.
  - `evidently`: Statistical drift testing (K-S test, Chi-square), S3 HTML/JSON/Summary reports, and automatic Continuous Training (`apps.ct`) trigger.

## Identifier Invariants

- Model packager: `BUILD_ID`
- Model serving and Evidently: Pair of `PROJECT_ID` and `MODEL_VERSION_ID`
- Training runner: `TRAINING_JOB_ID`
- Drift run: `DRIFT_RUN_ID`
- Never fallback to or introduce the legacy `MODEL_ID` variable.

## Validation

Execute the target service's isolated pytest suite with coverage as described in [testing.md](references/testing.md):
```bash
python -m pytest tests --cov=src --cov-report=term-missing
```
For Control Plane changes, also run Django checks and dry-run migration validation:
```bash
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
```
