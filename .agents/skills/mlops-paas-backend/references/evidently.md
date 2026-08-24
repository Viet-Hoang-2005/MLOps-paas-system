# Evidently

The Evidently runner creates drift reports from a reference dataset and production observations.

- Identity includes tenant context, `PROJECT_ID`, `MODEL_VERSION_ID`, and `DRIFT_RUN_ID`.
- Validate runtime configuration in `main`, never exit during module import.
- Load local or presigned HTTP CSV/Parquet data and handle download failure explicitly.
- Flatten production JSONB dictionaries/strings and attach predictions.
- Derive column mapping from MLflow signature, with careful dtype fallback.
- Reject datasets without common comparable columns.
- Generate HTML report, JSON report, and summary; upload all required outputs through scoped URLs.
- Reject ZIP path traversal and unsafe members.
- Callback carries run summary and uses authenticated/idempotent semantics.

Insufficient samples should become a controlled run failure, not terminate the test process.
