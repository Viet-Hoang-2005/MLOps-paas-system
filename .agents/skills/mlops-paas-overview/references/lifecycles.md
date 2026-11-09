# Core Lifecycles

## 1. Training Lifecycle (Untrusted Sandbox)

1. User creates an account-owned workspace without a Project, edits unified Input and separate Environment/Secrets, and chooses CPU/GPU/framework/runtime from capabilities.
2. POST /api/training-workspaces/{id}/runs/ saves a revision-checked immutable Input ZIP and creates a new owner/tenant-scoped job. Storage I/O is outside transactions; final revision validation and reservations commit before Celery dispatch.
3. Docker uses an asynchronous labeled helper and per-job volume; Kubernetes uses a trusted init container and emptyDir. Main training mounts Input read-only. Legacy jobs retain their original input_contract.
4. Runner installs root requirements.txt, fetches one-use job runtime configuration, and runs Python in writable Work. SM_CHANNEL_TRAIN names unified Input, SM_MODEL_DIR the official model, SM_OUTPUT_DIR supported metadata, MLOPS_WORK_DIR temporary work. No mlops SDK. Stream sanitized logs and experiment metrics; Docker/Prometheus provide runtime resource snapshots separately.
5. User process must succeed and model output pass path/link/type/count/size validation before packaging model.tar.gz and verifying upload. Trusted observation/reporting finalizes lifecycle; tenant stdout cannot authoritatively declare success. Missing model or failed upload fails the run.
6. Successful verified jobs may be assigned to a new/existing owned Project with output_revision. Save preserves Model Preview and immutable model/input; no automatic build/register/deploy. Retry creates a new job from original snapshots and revalidates current Secret access.
7. Project deletion stops active jobs, copies/checksums/checkpoints legacy training objects to tenant/job storage, then detaches and preserves jobs/logs/artifacts/quota before Project cleanup. Workspace deletion also preserves historical run snapshots.

## 2. Packaging & Build Lifecycle

1. **Trigger:** User creates a Build from a revision-checked project Preview or an assigned completed TrainingJob with available verified output. Project has one mutable Preview; Build copies all input assets into immutable build-scoped keys.
2. **Analysis:** `model-packager` downloads model artifacts from S3, detects model flavor (`sklearn`, `xgboost`, `pytorch`, `tensorflow`, `keras`), and normalizes to MLflow PyFunc format (`MLmodel`).
3. **Dockerfile Generation:** Automatically selects optimal base image:
   - Scikit-Learn / XGBoost $\rightarrow$ `machine-learning-serving` (FastAPI).
   - PyTorch / TensorFlow $\rightarrow$ `deep-learning-serving` (BentoML).
4. **Image Build:**
   - *Local:* Docker SDK builds image directly into Docker daemon.
   - *Production K3s:* Kaniko rootless builder compiles image without Docker socket and pushes to Harbor OCI Registry as `image-{project_uuid}:build-{build_uuid}`.
5. **Log Streaming & Callback:** Streams logs and marks the Build `ready`; no automatic registration. Explicit `POST /api/builds/<build>/register/` creates one immutable version idempotently, retaining source/reference/advanced assets and actual requirements.
6. **Deployment:** Only registered Builds deploy. Runtime names use deployment UUIDs. `ModelProject.active_deployment` changes only after readiness; a failed candidate leaves the old Running version serving. Stop old runtime after handoff and invalidate gateway cache.
7. **Overview/Drift:** Read the Running snapshot, never latest/Preview fallback. Monitors have immutable reference copies; replacing Running disables old automatic monitors but retains history. Creating a new monitor is manual.
8. **Deletion:** Disable the project first, stop jobs/runtimes, delete project-scoped images/objects/logs/cache, then hard-delete Project-owned DB rows. Training jobs/artifacts/logs/quota are preserved and detached after verified storage migration. Failures stay `delete_failed` and retry; no shared-image or bucket deletion.

## 3. Serving & Inference Lifecycle

1. **Routing Ingress:** Client sends inference request `POST /models/{version_id}/predict` to `model-server` Gateway.
2. **Authentication:** `model-server` checks access mode (`public`, `protected`, `private`), verifies Bearer JWT against Control Plane JWKS (`RS256`), or validates `X-API-Key` via Redis cache/PostgreSQL.
3. **Dynamic Worker Resolution:** Resolves worker target:
   - *Docker:* `http://<service_name>:<port>/predict`.
   - *Kubernetes:* CoreDNS FQDN `http://<deployment>.<namespace>.svc.cluster.local:<port>/predict`.
4. **Worker Execution:**
   - `machine-learning-serving` verifies feature signature columns, computes predictions, and calculates `confidence` via `predict_proba`.
   - `deep-learning-serving` normalizes tensor inputs and executes PyFunc predictions.
5. **Response & Asynchronous Telemetry:**
   - Returns prediction JSON to client immediately.
   - Asynchronously emits an inference telemetry event to Redpanda Kafka topic `mlops_paas_production_data` in `BackgroundTasks`.

## 4. Drift Monitoring & Continuous Training (CT) Lifecycle

1. **Ingestion & Outbox:** `consumer` worker micro-batches records from Kafka into PostgreSQL (`production_predictionrecord`). In the same transaction, writes a signal to `observability_eventoutbox`.
2. **Signal Dispatch:** An isolated background thread leases signals and notifies Control Plane via `POST /internal/webhooks/automatic-drift/`.
3. **Evaluation Trigger:** When accumulated samples reach threshold (`MIN_SAMPLES`), Control Plane dispatches an `Evidently` runner task.
4. **Statistical Analysis:** `evidently` compares reference data from S3 against current production data from PostgreSQL using statistical tests (Kolmogorov-Smirnov, Chi-square).
5. **Reporting:** Generates and uploads `report.html`, `report.json`, and `summary.json` to S3 via Presigned PUT URLs.
6. **Callback & Continuous Training:**
   - Calls `POST /internal/webhooks/drift-runs/<run_id>/` with `drift_share`.
   - If `drift_share > DRIFT_THRESHOLD`, Control Plane module `apps.ct` automatically triggers an automated retraining pipeline, launching a new `TrainingJob` with updated production data.
