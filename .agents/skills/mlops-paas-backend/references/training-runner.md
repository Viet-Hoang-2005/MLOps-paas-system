# Training Runner

The Training Runner (`services/training-runner/`) executes user-supplied training code in an isolated sandbox. User training code is treated as an **Untrusted Workload**.

## Core Responsibilities

1. **Identity Invariant:** Operates strictly with `TRAINING_JOB_ID`.
2. **Untrusted Code Sandbox:**
   - Never receives AWS credentials (`AWS_ACCESS_KEY_ID`), PostgreSQL credentials, or system Redis write access.
   - Operates solely through scoped Presigned S3 URLs and a short-lived, signed **Capability Token**.
3. **Workspace Isolation:**
   - Downloads source code and training dataset snapshots from S3.
   - Safely extracts archives into `/workspace/source` and `/workspace/input/train`.
   - Installs job requirements (`requirements.txt`).
4. **Subprocess Lifecycle & Process Group Cleanup:**
   - Executes main script (`ENTRY_POINT`, default: `train.py`) in an isolated subprocess.
   - Manages a dedicated process group (`os.killpg`). Upon receiving `SIGTERM` (job cancellation), terminates the entire process tree to prevent zombie processes and GPU memory leakage.
5. **Real-time Metric Protocol:**
   - Parses stdout/stderr for structured metric lines:
     `METRIC_JSON {"epoch": 1, "loss": 0.25, "accuracy": 0.94}`
   - Streams metric events and application logs to Redis (`training_logs:{job_id}`) or Grafana Loki.
   - Logs hyperparameter metrics and artifacts to MLflow Tracking Server.
6. **Output Bundling & Callback:**
   - Collects trained model artifacts (`/workspace/model/`), metrics, parameters, and model insights (`feature_importance.json`, `coefficients.json`).
   - Packages into `training_output.zip` and uploads to S3 using its Capability Token.
   - Dispatches authenticated callback to `/internal/webhooks/training-jobs/<id>/` reporting `COMPLETED` or `FAILED`.
