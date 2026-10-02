# Cross-Service Contracts

## 1. Environment ID Invariants

| Runtime / Worker | Required Identity Variables |
| --- | --- |
| **Model Packager** | `BUILD_ID`, `PROJECT_ID`, `TASK_TYPE`, `BUILD_ENGINE` |
| **ML & DL Serving** | `PROJECT_ID`, `MODEL_VERSION_ID`, `MODEL_URI` |
| **Evidently Drift** | `PROJECT_ID`, `MODEL_VERSION_ID`, `DRIFT_RUN_ID`, `TENANT_ID` |
| **Training Runner** | `TRAINING_JOB_ID`, `PROJECT_ID`, `ENTRY_POINT`, `CAPABILITY_TOKEN` |

> [!CAUTION]
> Never introduce or fallback to the ambiguous legacy `MODEL_ID` variable.

## 2. Storage & S3 Layout

Bucket: `mlops-paas-artifacts`

```text
users/{tenant_id}/models/{project_uuid}/
├── code/                                  # Current mutable workspace code
├── data/                                  # Current mutable workspace dataset
├── training/jobs/{job_uuid}/
│   ├── input/code/source.zip              # Immutable source snapshot
│   ├── input/data/train.csv               # Immutable data snapshot
│   ├── output/training_output.zip         # Packaged training artifacts bundle
│   └── mlflow/                            # MLflow run artifacts
├── versions/{version_uuid}/artifacts/     # Immutable registered model artifacts
└── drift/{monitor_uuid}/{run_uuid}/       # Evidently HTML/JSON/Summary reports
```

- All S3 uploads and downloads in runner jobs must use single-object scoped Presigned URLs with short expiration periods (e.g. 900 seconds).

## 3. Container Image Naming Contract

- **Local Docker:** `image-{project_uuid}:build-{build_uuid}`
- **Production Harbor:** `{HARBOR_REGISTRY_URL}/user-images/image-{project_uuid}:build-{build_uuid}`
- **Registered Version Tag:** `image-{project_uuid}:v{version_number}`
- **Immutable Digest:** Stored in database as registry digest (`sha256:...`) upon registration.

## 4. Webhook Callback Contract

1. **Path-bound UUID:** The target resource UUID must appear in the callback path (e.g. `/internal/webhooks/training-jobs/<uuid:job_id>/`).
2. **Authentication:** Authenticate via `Authorization: Bearer <CONTROL_PLANE_WEBHOOK_SECRET>`.
3. **Idempotency:** Include `Idempotency-Key` in request headers. Handlers use `select_for_update()` to ensure safe transitions.
4. **No State Resurrection:** Callbacks arriving after a resource has been `CANCELLED` or is `DELETING` must be treated as a no-op (return HTTP 200) and must never revive terminal states.

## 5. Telemetry & Ingestion Contract

- **Model Server:** Asynchronously emits inference telemetry to Redpanda Kafka topic `mlops_paas_production_data`. Kafka producer errors must be observable in logs and metrics, but must never cause the client inference request to fail.
- **Consumer:** Consumes Kafka records, normalizes UTC timestamps, flattens `features` JSONB, and bulk-inserts into `control_plane.production_predictionrecord` with `ON CONFLICT (id) DO NOTHING`.
- **Transactional Outbox:** In the same transaction as the production record insert, writes an automatic drift signal into `control_plane.observability_eventoutbox`.
- **Drift Dispatcher Thread:** Leases pending signals (`lease_seconds=60`) and dispatches HTTP POST requests to `CONTROL_PLANE_AUTOMATIC_DRIFT_WEBHOOK_URL` with exponential backoff without blocking the Kafka ingestion thread.
