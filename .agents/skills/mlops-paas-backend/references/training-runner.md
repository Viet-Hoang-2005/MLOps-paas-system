# Training runner

The training runner executes tenant-supplied code and must be treated as untrusted.

- Identity is `TRAINING_JOB_ID`.
- Download source/data through job-scoped presigned URLs.
- Safely extract archives and retain the complete source tree.
- Execute only the selected main script (`ENTRY_POINT`); it may import sibling modules.
- Install the job snapshot requirements with bounded behavior and clear logs.
- Emit progress/metrics without authority to set trusted terminal lifecycle state.
- Package model, metrics, params, insights, and metadata into the TrainingOutput bundle.
- Upload output with a job capability or scoped presigned URL.
- Never receive shared application secrets, AWS credentials, production Redis, or unrestricted MLflow credentials.

Cancellation and timeouts must terminate the process tree/container and remain idempotent.
