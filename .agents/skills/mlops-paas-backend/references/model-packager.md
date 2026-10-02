# Model Packager

The Model Packager (`services/model-packager/`) packages raw model files into MLflow-compatible container images. It is executed as an on-demand task worker (via Docker SDK locally or an Argo Workflow in production) and does not expose a public HTTP API.

## Core Responsibilities

1. **Identity Invariant:** Operates strictly with `BUILD_ID`.
2. **Model Normalization:**
   - Detects model files: `.pkl`, `.joblib`, `.xgb`, `.pt`, `.pth`, `.h5`, `.keras`.
   - Identifies flavor (`sklearn`, `xgboost`, `pytorch`, `tensorflow`, `keras`) and standardizes into MLflow PyFunc format (`MLmodel`).
3. **Automated Dockerfile Generation:**
   - Automatically selects optimal base image:
     - Scikit-Learn / XGBoost $\rightarrow$ `machine-learning-serving` (FastAPI).
     - PyTorch / TensorFlow $\rightarrow$ `deep-learning-serving` (BentoML).
   - Injects user requirements (`requirements.txt`, conda `environment.yml`).
4. **Dual Build Engine:**
   - *Local (`BUILD_ENGINE=docker`):* Uses Docker SDK (`docker-py`) to build image into local Docker daemon.
   - *Production K3s (`BUILD_ENGINE=kaniko` via 3-step Argo DAG):*
     - Step 1 (`TASK_TYPE=BUILD`): Prepares Dockerfile and context in shared `/workspace/`.
     - Step 2 (`kaniko-executor`): Performs rootless container build without Docker socket and pushes to Harbor OCI Registry as `image-{project_uuid}:build-{build_uuid}`.
     - Step 3 (`TASK_TYPE=NOTIFY_BUILD`): Reads build result from `/workspace/` and dispatches webhook callback to Control Plane.
5. **Security & Archive Extraction:**
   - Enforces strict Zip/Tar Slip protection (`safe_extract_tar` rejects `..`, absolute paths, and dangerous symlinks).
   - Operates with Presigned S3 URLs; zero AWS credentials inside container.
   - Dependency installation failures must fail the build; never hide pip errors behind shell `|| echo`.
6. **Real-time Log Streaming:** Streams build output line-by-line into Redis (`build_logs:{build_id}`) for UI progress display.
