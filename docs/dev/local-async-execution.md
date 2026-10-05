# Local asynchronous Build and Deploy

Docker Compose uses the existing Control Plane image and Celery services. No
additional orchestrator is needed. Production Argo submission/callback behavior
is unchanged.

| Operation | Local execution | Confirmation |
| --- | --- | --- |
| Build | Start detached Model Packager; return `dispatched` | Authenticated, validated build callback |
| Training | Start detached Training Runner | Existing short status polls |
| Deploy | Start runtime from registered immutable image | Short Control Plane readiness probes |
| Runtime health | Observe only the Running succeeded deployment | Separate `runtime-health` queue, consumed by the shared local worker |

## Scheduling and state

Apply deployment migration `0008` before restarting the application processes.
It adds nullable deadline, next-check and lease fields, plus the Build callback
grace deadline; it does not rewrite old rows. New local attempts use the new
contract; in-flight old attempts are not adopted. Finish or cancel them using the
old code before updating, or use a clean local application DB.

Compose enables `LOCAL_EXECUTION_WATCH_ENABLED=true` only on its existing Beat.
Every five seconds Beat enqueues a DB-only scan into `celery`. The scan claims
due Docker executions and dispatches short check tasks. Each delivery expires
after ten seconds and has a single-use, thirty-second DB lease. A checker has a
20s soft / 25s hard time limit. Expired leases or failed publication are recovered
by the next scan. Checks remain in the ordinary worker with Docker access; the
Beat does not mount the Docker socket or receive new secrets. Local
`celery-worker` consumes both `celery` and `runtime-health` with concurrency 2;
the two queues share these two execution slots. No separate local health worker
is needed. Health tasks can be delayed under load; existing task expiry, leases
and 45-second health freshness still apply. Production keeps its dedicated
health worker and separate queue consumption unchanged.

When updating an existing local stack, the removed health service may leave an
orphan container. Identify it with
`docker ps -a --filter label=com.docker.compose.service=celery-health-worker`, verify the Compose project
label, then stop/remove only that confirmed old container. Do not use blanket
`--remove-orphans`: detached build/training/model containers may share the network
and must not be indiscriminately cleaned up. Recreate `celery-worker` and
`celery-beat` after applying the configuration; no volume reset is needed.

Build defaults to `LOCAL_BUILD_TIMEOUT_SECONDS=43200` (12 hours). Deploy readiness
defaults to `LOCAL_DEPLOY_READINESS_TIMEOUT_SECONDS=90`, measured from first runtime
creation; duplicate dispatch does not extend it. These values are passed to the
ordinary worker by Compose. A readiness probe uses the same bounded HTTP checker
as monitoring (connect 1s/read 2s, no redirects, maximum 64 KiB, strict model identity).

## Build completion

Model Packager retries transient callback delivery up to three times with the
same idempotency key and bounded HTTP timeouts. Permanent HTTP errors are not
retried. Neither exceptions nor logs include callback headers, URLs or payloads.
The local success callback must provide the expected build-scoped image tag,
SHA-256 digest, nonempty package manifest and the already assigned package URI
(if it sends that URI). The API does not register an Evolution version.

Docker exit `0` alone is not success. After the runner exits, the watcher gives
a valid callback 30 seconds to arrive; otherwise the Build fails with a missing
confirmation error. Nonzero exit, disappearance or execution timeout fail the
attempt. Duplicate/late callbacks cannot revive terminal builds. A `ready` Build
is never overwritten by an exit observation.

The watcher retains a bounded, sanitized log tail and removes the runner only
after it exits (or must be stopped). Failed/cancelled outputs are cleaned only
after the producer is stopped. Cleanup failure does not overwrite a successful
Build. Execution deadlines are persisted rather than inferred from task retries.

## Deploy readiness versus monitoring

The dispatch task creates the runtime and Endpoint (`unknown`) and returns;
there is no sleep/readiness loop in the Docker backend. A due check inspects the
owned container, then probes once. Failed readiness reschedules, not sleeps.
ML uses GET `/health`; DL uses POST `/health` with `{}`. Readiness requires HTTP
200, `status=healthy`, `model_loaded=true` and matching project/version identity.

Successful readiness marks lifecycle `succeeded` and switches Running through
the existing transition service. Missing/dead runtime or an expired deadline
fails only the candidate and schedules its cleanup; the previous Running stays.
Results arriving after stop, deletion, lease expiry or readiness deadline cannot
promote the candidate. The model runtime receives no callback authority.

After success, readiness checking ends. Continuous runtime health remains
independent and never changes lifecycle or Running. An unhealthy API after
deployment still has deployment lifecycle `succeeded`.

## Failure and safety

Container names are generated from execution UUIDs and protected by tenant,
project and build/deployment labels. Redelivery reuses only the same labelled
attempt. A missing recorded container is not silently recreated. Foreign or
changed identities fail closed; cleanup never deletes them.

Docker or observer outage is retried without fabricating a model failure.
After the execution deadline the lifecycle may fail with an explicit deadline
reason, but cleanup keeps retrying until Docker can be contacted safely. A late
cleanup cannot turn `ready`/`succeeded` into failure. Restart recovery requires
PostgreSQL and the broker to retain their state.

## Local acceptance smoke (run manually)

1. Apply migrations and restart API, shared local worker and Beat.
2. Start two builds and a deploy; verify ordinary workers finish dispatch and
   continue handling short tasks while runner/runtime containers are active.
3. Close Web: Build/readiness must still finish and logs remain available later.
4. Restart only the ordinary worker during execution; verify the scanner resumes
   watching and no duplicate container appears.
5. Test success, runner failure, missing callback, delayed model startup and
   readiness timeout. Register remains a separate user action.
6. Stop/delete during a readiness probe. Verify no late result restores Running.
7. Deploy a failing candidate while an old version is Running; verify it remains
   Running. Make its API unhealthy and recover it: only health changes.
8. Verify failed/cancelled build cleanup, image retention for registered builds
   and removal of finished packager containers.

Unit tests use mocked Docker, HTTP, broker, storage and registry clients. Passing
them is not a claim that these destructive/end-to-end smoke steps were run.
