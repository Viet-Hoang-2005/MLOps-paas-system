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
