# System Architecture

## System Planes

The platform is structured into distinct, decoupled operational planes:

- **Control Plane:** A domain-oriented Django Modular Monolith (`services/control-plane/`) with Celery background workers. Manages authentication, identity, API keys, workspaces, model catalog, immutable registry versions, training jobs, packaging builds, deployments, drift monitors, continuous training policies, and observability. Dispatches async jobs at `transaction.on_commit`.
- **Data & Serving Plane:** Centralized inference gateway (`services/model-server/`) that verifies JWT/JWKS or project-scoped API keys, dynamically resolves worker URLs, proxies inference traffic to stateless model workers, and asynchronously publishes production telemetry events to Redpanda Kafka.
- **Inference Worker Runtimes:**
  - `machine-learning-serving`: FastAPI worker specialized for classical tabular ML models (Scikit-Learn, XGBoost, LightGBM) loaded via MLflow PyFunc.
  - `deep-learning-serving`: BentoML worker specialized for deep learning models (PyTorch, TensorFlow, Keras) with tensor I/O normalization.
- **Data Ingestion & Drift Plane:**
  - `consumer`: High-throughput background worker consuming inference telemetry from Redpanda Kafka (`mlops_paas_production_data`), micro-batching records into PostgreSQL (`production_predictionrecord`), and maintaining a Transactional Outbox (`observability_eventoutbox`) with a supervised dispatcher thread signaling Control Plane.
  - `evidently`: Standalone runner performing statistical drift tests (K-S test, Chi-square) comparing S3 reference datasets against current production observations. Automatically triggers Continuous Training (`apps.ct`) when drift exceeds thresholds.
- **Execution Plane:** Dual-backend execution engine:
  - *Local Development:* Docker Engine via Docker SDK (`EXECUTION_BACKEND=docker`).
  - *Production K3s:* Argo Events, Argo Workflows DAGs, Kaniko rootless image builder, Kubeflow Training Operator (`PyTorchJob`), and Karpenter elastic GPU/CPU node autoscaler (`EXECUTION_BACKEND=argo`).
- **Storage Plane:**
  - PostgreSQL (schema `control_plane`): Relational Source of Truth (SSOT) for all domain entities and production inference records. CloudNativePG in production.
  - AWS S3 (`mlops-paas-artifacts`): Object store for immutable code/data snapshots, training output bundles, registered model artifacts, and Evidently HTML/JSON reports.
  - Redis: Celery broker, task result backend, transient real-time runtime log stream (`training_logs:*`, `build_logs:*`, `drift_logs:*`), and Model Server cache. Supports Redis Sentinel HA in production.
  - Harbor: OCI private container registry for built model images (`image-{project_uuid}:build-{build_uuid}`).
- **Observability Plane:** Kube-Prometheus-Stack, Grafana dashboards, Grafana Loki (production centralized log aggregation with signed task-bound cursor proxy in Control Plane), and Prometheus health/metrics endpoints (`/health/live`, `/health/ready`, `/health/metrics`).

## State Ownership

1. **PostgreSQL** owns all domain states, lifecycle transitions, and production telemetry records.
2. **AWS S3** owns object payloads: code snapshots, datasets, model weight artifacts, and drift reports.
3. **Harbor / OCI Registry** owns container image manifests and layers.
4. **Redis** is strictly a cache, message broker, and presentation log buffer; it must never be treated as the persistent source of truth.

## Identifier Invariant

- `tenant_id` (UUID): Tenant boundary and public inference routing.
- `project_id` (UUID): Model project workspace and mutable assets.
- `model_version_id` (UUID): Immutable registered model version.
- `build_id` (UUID): Single container packaging attempt and log stream.
- `deployment_id` (UUID): Single serving rollout attempt and runtime endpoint.
- `training_job_id` (UUID): Single immutable training execution.
- `drift_run_id` (UUID): Single statistical drift report execution.

## Strict Layering Pattern

```text
HTTP Request
  ──► Serializer (Input validation)
  ──► Selector / Service (Tenant check & business logic)
  ──► transaction.atomic (PostgreSQL write, status=PENDING/RUNNING)
  ──► transaction.on_commit (Celery task dispatch AFTER DB commit)
  ──► Celery Worker (Backend execution factory: Docker or Argo)
  ──► External Runner Container (Training Runner / Packager / Evidently)
  ──► Internal Webhook Callback (select_for_update, Idempotency-Key)
  ──► Final Status Transition (COMPLETED / FAILED)
```
