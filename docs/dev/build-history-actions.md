# Deployment build history actions

The Deployment table has an Actions column with Re-build and Delete, including
confirmation dialogs in English and Vietnamese.

## Re-build

`POST /api/builds/<build UUID>/rebuild/` creates a new Build and leaves the old
Build and registered versions intact. Preview builds use the **current Preview**
(not the old input snapshot, which may already have been purged after failure).
Training builds use the original completed TrainingJob and its frozen output;
deleted/purged training output is rejected. The new build opens in the deployment
wizard with its own log stream. Running builds, registration in progress, and
build/project cleanup cannot be rebuilt. An existing active build for the same
TrainingJob is reused by the existing training build contract.

## Delete

`DELETE /api/builds/<build UUID>/` accepts every unregistered build state,
including successful images and active builds, and returns HTTP 202. Ownership
is checked before the lookup. Registered/registration-in-progress builds and
builds referenced by Deployments return HTTP 409; Evolution is never changed.

The service persists `deletion_state=deleting` and enqueues Celery cleanup after
commit. The worker locks project then Build, rechecks registration, quiesces the
runner, deletes the canonical `image-<project>:build-<build>` image/tag and the
build-scoped S3 prefix, then hard-deletes the Build and its input asset rows.
Project Preview, training output and other builds are not deleted. Transient
Redis log buffers expire through their existing TTL; Loki retention is unchanged.

Local Docker cleanup removes only the known `build-<UUID>` runner and uses
non-forced image deletion. Harbor cleanup preserves an artifact with other
version/build tags: only the deleted build's tag is removed. Unshared Harbor
artifacts are deleted; physical shared blob reclamation still belongs to Harbor
garbage collection. Registry/storage failures retain a retryable record and
are retried with backoff. A final failure remains visible as Cleanup failed;
the user can retry Delete. Do not remove DB rows manually to hide cleanup errors.

The current Events-only Argo build backend has no confirmed cancellation API.
For a dispatched Argo build, deletion waits for a trusted terminal webhook
(`execution_completed_at`), even when a previous cancel request already changed
the public status to cancelled. The webhook cannot revive a deleting build and
reschedules cleanup. If the Workflow never reports completion, cleanup fails
closed instead of deleting an image while Kaniko may still publish it.

API/worker code must be deployed together after migration
`deployment.0006_build_deletion_state`. This change is local code only; it does
not delete existing model builds or apply changes to a cluster.

## Validation

- Control Plane: `pytest src/apps/deployment/tests src/apps/catalog/tests
  src/apps/training/tests src/apps/registry/tests`.
- Frontend: `pnpm test:build-actions`, `pnpm lint`, `pnpm build`.
- Manually smoke the two confirmations, busy/registered states, failure retry,
  successful-image deletion and new-build log navigation on Docker Compose.
