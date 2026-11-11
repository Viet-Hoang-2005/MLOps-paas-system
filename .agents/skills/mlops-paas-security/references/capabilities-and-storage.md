# Capabilities and storage

Training capabilities are random bearer capabilities whose SHA-256 hash—not plaintext—is stored.

- Bind token to one TrainingJob and purpose.
- Use a short expiry.
- Make terminal/reporting capabilities one-time where appropriate.
- Reject wrong job, wrong purpose, expiry, and replay.
- Purposes include output upload, trusted reporting, and cancellation reporting.

Presigned URLs:

- Scope to one object/key or narrow job prefix.
- Scope to one operation: GET or PUT, never broad list access.
- Use short TTLs.
- Generate server-side object keys.
- Do not put AWS credentials in tenant pods.
- Validate archive paths before extraction and uploaded content metadata before use.

S3 prefixes must include tenant and project/job/version/run identities to prevent collisions and simplify deletion.

## Project-independent training

Authorize job workspace reads and mutations by owner, never only through an optional Project. New object prefixes use tenant/job UUIDs. Legacy storage_project_id remains immutable; assigning a Project must not move objects or change runtime labels. Stop active jobs and copy/checksum/checkpoint legacy storage before Project cleanup; preserve training records, logs and quota.

Input must be an actual read-only mount in Docker and Kubernetes. Use a trusted helper/init stage and distinct writable Work/model/output. Validate the model tree before metadata/tracking and archive upload; reject links and special files, and do not deserialize tenant models to validate them.

Secrets are Fernet-encrypted with a separate backend-only key. Reading APIs expose names/metadata only. Keep plaintext out of Input/downloads/events. Runtime configuration uses a job-bound expiring one-use capability; reject replay, stopping/deleting jobs, reserved environment names and cross-job access. Snapshot at submit, revalidate current Secret permission on retry, and redact known values in streamed and captured logs. Explicitly explain that code receiving Secrets can intentionally disclose them.

Editing/unsubmitted preparation cannot receive runtime capabilities. A job owns its draft entries/Secrets and one execution. Clone/retry use a new job UUID and current source Secret rows; never recover revoked values from historical snapshots.
