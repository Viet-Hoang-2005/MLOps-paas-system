# P1 Execution Recovery

## Runtime Contract

PostgreSQL is authoritative for TrainingJob and DriftRun dispatch, observation and
cleanup. Redis carries tasks/logs and may be cleared without losing committed jobs.
`EXECUTION_WATCH_ENABLED=true` enables a 15-second Beat scan, batches of 100 per
resource kind, `select_for_update(skip_locked=True)` and 60-second leases. Only one
Beat instance should run. Observations are applied only while their lease is valid.
Docker/HTTP/S3 operations occur outside observation transactions.

`queued` resources are dispatched again after a lost enqueue; `running` resources
are observed again after worker restart or polling-task loss. Docker names are
`training-<UUID>` / `drift-<UUID>`. Every adoption, stop and removal checks tenant,
project, resource labels and any stored runtime ID. A container left in `created`
is started again; a running/exited container is adopted. Ownership errors require
operator investigation and never authorize removing another resource.

Temporary connection/timeout errors keep the lifecycle status and retry after
5, 10, 20, 40, then 60 seconds. The periodic scan may add up to 15 seconds of delay.
An exit code, confirmed missing runtime, invalid resource configuration, missing
terminal artifacts or exceeded deadline can fail the job. Failure/cancellation
and durable stop intent commit before cleanup; backend outages retain cleanup
intent. Training deletion waits for runtime cleanup. Duplicate/late callbacks do
not revive cancelled, failed or deleted resources.

The public APIs retain lifecycle enums and add `observation_status` (`ok`,
`retrying`, `cleanup_pending`), `observation_error`, `runtime_started_at` and
`execution_deadline_at`. Web polls authoritative status independently of logs.

## Training Configuration

CPU/memory profiles are 1/2048, 2/4096 and 4/8192 (cores/MiB), validated on
create/update/submit. Runtime options are 900, 1800, 3600, 7200, 21600, 43200 seconds
and come from `GET /api/training-jobs/runtime-capabilities/`. GPU requires
`TRAINING_GPU_ENABLED` and a count in `TRAINING_GPU_COUNTS`; `none` requires 0.
Docker sets CPU quota, memory plus swap limit and GPU DeviceRequest. An unavailable
GPU fails explicitly; no CPU substitution occurs.

`EXECUTION_DISPATCH_TIMEOUT_SECONDS` defaults to 1800. Runner runtime begins when
its container process starts, including Python initialization, input download,
pip, training and output upload. The supervisor signals the entire child process
group with SIGTERM, waits at most 30 seconds, then SIGKILLs remaining descendants.
The external observer also stops a runtime that exceeds its deadline. After a
queue outage, actual runtime start/finish timestamps distinguish node wait from
execution time, including completion before the deadline observed later.

Capability TTL is dispatch wait + runtime + 900 seconds grace, capped at 46800
seconds (13 hours). Presigned URLs default to 900 seconds. The runner obtains
fresh input URLs at startup, then an output PUT URL just before upload, with
`Content-Type: application/gzip`. Dispatch retry does not revoke tokens already
given to an accepted workload. Drift runtime defaults to 3600 seconds.

## Stack Checks

Check each path independently; Control Plane readiness does not prove ingress or
telemetry is healthy:

```powershell
curl.exe --fail http://localhost:8000/health/ready
docker exec traefik traefik healthcheck --ping
curl.exe --fail http://localhost:5001/health/ready
docker exec redpanda rpk cluster info -X brokers=localhost:9092
docker compose ps
```

Control Plane readiness checks its PostgreSQL/Redis dependencies. Gateway readiness
uses the directly published gateway port 5001; port 5002 routes inference through
Traefik and does not expose the gateway readiness path. Gateway readiness
checks PostgreSQL, Redis and Kafka metadata with short timeouts and returns 503 on
failure. `/health/live` and the gateway root remain liveness checks. Confirm an
actual inference result reaches the consumer/PostgreSQL production records to
prove telemetry ingestion beyond Kafka connectivity. Traefik and Redpanda have
restart policies and independent healthchecks.

Browser inference uses no credentials/cookies, current Bearer access and a
30-second timeout. Only the gateway's expired-token 401 causes one Control Plane
refresh; permission errors, network failures and gateway timeouts retain session.

## Validation

```powershell
docker build -t mlops-paas-training-runner:latest services/training-runner
docker exec control_plane python manage.py shell -c "exec(open('scripts/smoke_p1_execution.py').read())"

# Optional hardware acceptance when the Docker host supports NVIDIA GPU:
docker exec -e P1_SMOKE_GPU=1 control_plane python manage.py shell -c "exec(open('scripts/smoke_p1_execution.py').read())"
```

This creates a disposable project/account, uses scoped real S3 objects, verifies
training resource limits and runtime-ID recovery, stops an overdue runtime, and
runs actual Evidently with 100 synthetic prediction records. Its `finally` removes
only its owned runtimes, objects and records. It does not clear application Redis,
volumes or existing projects. Run only on local Compose.

`services/training-runner/tests/runtime_smoke.py` runs inside the Linux runner image
with an isolated HTTP server. Pass `download`, `pip`, `train`, `upload` or `success`,
mount the tests read-only and set `--cpus 2 --memory 4096m --memory-swap 4096m`.
Short deadlines are test-only; public runtime choices remain unchanged.

Local acceptance on 2026-10-07 verified browser public/private inference,
cookie omission, expired-token refresh, permission/timeout session retention;
actual Docker CPU/RAM cgroups, supported GPU DeviceRequest/hardware visibility;
deadline shutdown during download/pip/train/upload and descendant termination;
training artifact recovery and an actual Evidently run with scoped reports.
The GPU smoke affects its disposable process only; it does not enable GPU for the
whole stack. PostgreSQL tests cover concurrent lease claims, observation replay
and cancellation/completion serialization. Argo acceptance remains offline;
cluster smoke below is required before production enablement.

Backend regression uses `config.settings.test`. Lease concurrency requires
`config.settings.integration_postgres` with `PGTEST_HOST/PORT/DB/USER/PASSWORD` pointing to
a separate disposable PostgreSQL server. Never point these at application data.
Run `web/scripts/test-inference.mjs` for isolated client regression. Browser smoke
is `web/scripts/smoke-inference-browser.mjs`; set `P1_PLAYWRIGHT_MODULE` to the
installed Playwright `index.mjs`, install Chromium and run the existing Vite server
at `http://localhost:5173`. Fixture tokens are consumed in memory and must not be
logged or retained. If interrupted, invoke `p1_inference_fixture.py` with
`P1_FIXTURE_MODE='cleanup'` and remove only `mlops-p1-inference-*` test containers.

## Argo Smoke And Rollout

Argo is validated offline only. Render `k8s/argo` and the production Control Plane
overlay; run `python -m k8s.validate.run_all` plus `pytest k8s/validate/tests` with
kubectl/Kustomize, Helm and kubeconform available. The trusted submit workflow
creates/adopts one owned `training-<UUID>` / `drift-<UUID>` Workflow. Sensor forwards
the entire validated event body, including runtime and input capability. The
training template retains CPU/RAM/GPU requests/limits. Reconcile reads Workflow,
PyTorchJob and main-container timestamps, then reports via a 60-second signed
resource/tenant/project/lease capability. Replay and expired leases are denied.
Stop-before-submit creates a Git-managed terminated Workflow tombstone that is kept for
7 days (`TOMBSTONE_TTL_SECONDS`), far beyond the replay window of the submit event.

On a staging cluster, verify duplicate train/drift events reuse the same Workflow
UID and PyTorchJob/Pod UID; deliberately send wrong ownership and confirm denial.
Exercise pending node beyond dispatch deadline, runtime beyond execution deadline,
worker/Redis outage, callback replay and cancellation concurrent with completion.
Confirm output recovery from this run's S3 prefix and eventual workload cleanup.
Check operations service-account RBAC in `mlops-execution` and `user-jobs`, with
no Secrets or pods/exec access. Control Plane must have no Kubernetes credentials.
Pre-pull the small operations image and reserve capacity so reconcile callbacks
can arrive within the 60-second lease; expired reports are retried safely.
Retain actual Workflow/tombstone names through the event replay window; deleting
them manually also deletes create-if-absent history.

Roll out: additive migrations, runner/adapters and Argo templates, backend/Beat,
then FE. Inventory all active jobs before enabling the watchdog. Existing unlabeled
Docker runtimes require an ownership audit rather than automatic label adoption.
Production `EXECUTION_WATCH_ENABLED` stays false until the staging handlers/images
are compatible and cluster smoke has passed. While it is false, Argo training and
drift are not status-polled; their terminal status arrives only through callbacks.
Use the normal image promotion workflow; do not change pinned production digests
to a local image. No production deployment is performed by this P1 change.

`/metrics` exposes `control_plane_execution_jobs{kind,state}` for dispatch waiting,
expired leases, observation errors, deadlines and cleanup pending. Investigate
increasing counts and verify recovery after dependency restoration. Rollback may
disable the watchdog only after accounting for running work and pending cleanup;
keep the additive schema and retained runtime identities.
