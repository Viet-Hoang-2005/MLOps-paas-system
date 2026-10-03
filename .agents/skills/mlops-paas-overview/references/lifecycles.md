# Core Lifecycles

## 1. Training Lifecycle (Untrusted Sandbox)

1. **Submission:** User submits a training job via `POST /api/training-jobs/`.
2. **Snapshotting:** Control Plane snapshots source code and training dataset into immutable ZIP files in S3 under `users/{tenant}/models/{project}/training/jobs/{job}/input/`.
3. **Capability Generation:** Control Plane persists the job with status `PENDING` and generates a signed, short-lived **Capability Token**.
4. **Dispatch:** At `transaction.on_commit`, Celery dispatches the task:
   - *Docker:* Runs `training-runner` container on the local network.
   - *Argo:* Emits an event to Argo Events to launch a Kubeflow `PyTorchJob` on K3s with GPU tolerations (Karpenter auto-provisions GPU nodes).
5. **Execution:**
   - `training-runner` downloads snapshots via Presigned GET URLs using the Capability Token.
   - Extracts into `/workspace/source` and `/workspace/input/train`.
   - Installs dependencies from `/workspace/source/requirements.txt`.
   - Spawns subprocess to run `ENTRY_POINT` (e.g. `train.py`).
   - Streams stdout/stderr logs into Redis (`training_logs:{job_id}`) or Grafana Loki.
   - Parses real-time metric lines: `METRIC_JSON {"epoch": 1, "loss": 0.25}`.
6. **Output Bundling:** On success, packages `/workspace/model/`, metrics, parameters, and insights (`feature_importance.json`) into `training_output.zip`.
7. **Upload & Callback:**
   - Requests a Presigned PUT URL using its Capability Token and uploads to S3.
   - Calls `POST /internal/webhooks/training-jobs/<id>/` with shared secret.
   - Control Plane locks the job and transitions to `COMPLETED`; it does not register a version automatically. Reference CSV is frozen separately from training data; retries copy original snapshots into a new job.

## 2. Packaging & Build Lifecycle

1. **Trigger:** User creates a Build from a revision-checked project Preview or completed TrainingJob. Project has one mutable Preview; Build copies all input assets into immutable build-scoped keys.
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
8. **Deletion:** Disable the project first, stop jobs/runtimes, delete project-scoped images/objects/logs/cache, then hard-delete dependent DB rows. Failures stay `delete_failed` and retry; no shared-image or bucket deletion.

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
