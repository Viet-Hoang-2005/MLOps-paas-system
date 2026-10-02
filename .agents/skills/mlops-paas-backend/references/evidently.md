# Evidently

The Evidently runner (`services/evidently/`) performs statistical data and prediction drift analysis comparing reference datasets against production observations.

## Core Responsibilities

1. **Identity Invariant:** Requires `TENANT_ID`, `PROJECT_ID`, `MODEL_VERSION_ID`, and `DRIFT_RUN_ID`.
2. **Read-Only Database Access:**
   - Queries production inference records via `DB_HOST_RO` using a read-only database user.
   - Never writes or executes DDL on the primary database.
3. **Data Preparation & Guard Checks:**
   - Downloads reference dataset from S3 (`REFERENCE_DATA_URL`) supporting CSV and Parquet.
   - Queries up to `MAX_SAMPLES` production observations from `production_predictionrecord`.
   - If production samples are below `MIN_SAMPLES` (default: 100), reports controlled `insufficient_samples` status without crashing.
   - Flattens JSONB `features` into clean tabular data and derives `ColumnMapping` matching MLflow Model Signatures.
4. **Statistical Drift Testing:**
   - Executes Evidently AI (`Report(metrics=[DataDriftPreset()])`).
   - Applies appropriate statistical hypothesis tests (Kolmogorov-Smirnov / Wasserstein for numerical, Chi-square / Jensen-Shannon for categorical).
   - Calculates `drift_share = drifted_features / total_features`.
5. **Multi-Format Report Generation:**
   - Generates interactive HTML report (`report.html`), detailed JSON report (`report.json`), and quick summary JSON (`summary.json`).
   - Uploads all 3 reports to S3 via Presigned PUT URLs (`HTML_UPLOAD_URL`, `REPORT_JSON_UPLOAD_URL`, `SUMMARY_JSON_UPLOAD_URL`).
6. **Callback & Continuous Training Trigger:**
   - Dispatches authenticated webhook callback to Control Plane with drift metrics.
   - If `drift_share > DRIFT_THRESHOLD`, Control Plane module `apps.ct` automatically triggers an automated retraining pipeline.
