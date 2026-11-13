# Control Plane

The Django Control Plane is a domain-oriented modular monolith (`services/control-plane/`). It owns identity, authorization, relational source of truth (PostgreSQL schema `control_plane`), presigned storage URL generation, task dispatch, and trusted callbacks.

## App Ownership

Local training advertises Docker-derived CPU and memory profiles. Admission uses durable shared CPU/RAM reservations, Redis dispatch locking and a bounded available-memory probe; retain reservations until confirmed cleanup. Production CPU profiles and weekly quotas remain separate.

Training resource capabilities expose at most one GPU. Argo jobs require `accelerator_model` `t4` or `a10g`; Docker jobs require a currently verified NVIDIA device UUID in local_gpu_id and an empty accelerator_model; dispatch must request that exact device without fallback. CPU jobs use no model. Persist the model and retain it on retry; old Argo GPU jobs without a model cannot be submitted or retried.

1. **`auth`:** CustomUser, user profile avatars, RS256 JWT issuance, JWKS endpoint (`/api/auth/.well-known/jwks.json`), OAuth2 (Google/GitHub), 2FA/TOTP.
2. **`access`:** Project-scoped API keys (`ApiKey`) hashed with SHA-256 for machine-to-machine authentication.
3. **`catalog`:** Project metadata, one revision-checked `ModelPreview` per project, legacy project workspace assets, Running snapshot access, async retryable hard deletion.
4. **`registry`:** Immutable registered versions (`ModelVersion`), artifacts, metrics, insights, dynamic aliases (`champion`/`challenger`).
5. **`training`:** Account-owned `TrainingJob` drafts and executions (one UUID, one owned workspace, at most one submission) with optional Project links, short-lived Capability Tokens, Presigned S3 URLs, resource quotas, graceful cancellation.
6. **`deployment`:** Immutable Build input snapshots, explicit asynchronous idempotent registration, serving deployment/readiness. Project.active_deployment is the Running source of truth; runtime uses deployment UUID, not Build UUID.
7. **`drift`:** Drift monitors (`DriftMonitor`), scheduled and event-driven drift runs (`DriftRun`), report access, threshold configuration.
8. **`ct` (Continuous Training):** Retraining policies, automated retraining triggers (`RetrainingTrigger`), pipeline orchestration upon drift signals.
9. **`production`:** Production inference records (`ProductionPredictionRecord`), telemetry datasets, schema coordination with Consumer worker.
10. **`observability`:** Health endpoints (`/health/live`, `/health/ready`), Prometheus metrics (`/health/metrics`), transactional event outbox, runtime log proxy.

## Browser Authentication Contract

- GitHub OAuth account creation/linking must use a verified primary email from the authenticated `/user/emails` API, never the profile email; follow pagination through a bounded set of requests to the fixed GitHub endpoint and fail closed if verification is unavailable.

- Refresh validates the signed token's current user and tenant before issuing access or rotating refresh. Reject inactive, soft-deleted, missing users and invalid identity claims with `TokenError` (the endpoint returns `token_not_valid`); lock the account within the issuance transaction and never create orphaned outstanding tokens.
- Refresh rotation must atomically claim the old token by a unique blacklist insert; reject an already claimed token even if it passed the earlier validation. Commit that claim and the new outstanding token in the same transaction. Test concurrent refresh and concurrent revocation against disposable PostgreSQL.

- Browser sign-in endpoints return the short-lived RS256 access token in JSON and set the rotating refresh token only in a host-only `HttpOnly` cookie. Never return refresh tokens in JSON or persist either token in browser storage.
- Refresh and logout read the refresh cookie and require the exact configured Web `Origin` plus `X-Requested-With: XMLHttpRequest`; cookie-setting password, OAuth, and registration-completion endpoints enforce the same request checks.
- Logout blacklists a valid refresh token before clearing its cookie. Treat persistence failures as server errors so the Web can distinguish local logout from server-side revocation.
- Model Server remains a stateless Bearer-token verifier and does not consume browser cookies.

## Strict Layering Pattern

```text
HTTP Request
  ──► Serializer (Input validation)
  ──► Selector / Service (Tenant scoping & business logic)
  ──► transaction.atomic (PostgreSQL write, status=PENDING/RUNNING)
  ──► transaction.on_commit (Celery task dispatch AFTER DB commit)
  ──► Celery Worker (Backend execution factory: Docker or Argo)
  ──► External Runner Container (Training Runner / Packager / Evidently)
  ──► Internal Webhook Callback (select_for_update, Idempotency-Key)
  ──► Final Status Transition (COMPLETED / FAILED)
```

- API views must not directly call Docker, S3, Harbor, Argo, or Redis.
- Avoid circular imports by placing task imports at dispatch boundaries or moving shared queries to selectors.
- Use `select_for_update()` when transitioning terminal states to prevent race conditions.
- Late callbacks must never revive cancelled or deleting resources (return HTTP 200 no-op).
- Lock project before Preview/Build/job when coordinating deletion or snapshots; dispatch after commit. Normal new project requires artifact; training assignment may create a Project without Preview. Training ownership migrations and legacy storage preservation are additive; do not reset data.
- Keep raw/package artifact, requirements, source/reference and Advanced assets immutable across Build → Register; training retry uses original snapshots, not current workspace. Only registered versions deploy, and failed deployments retain old Running.
- Build history Re-build creates a new attempt from current Preview or original training output. DELETE persists a cleanup tombstone, blocks registration, and removes only unregistered build-scoped images/objects before hard deletion; dispatched Argo builds wait for a trusted terminal reporter. See `docs/dev/build-history-actions.md`.

## Runtime Logs Architecture

Local runtime metrics are read-only Docker SDK snapshots of the project's explicit Running deployment, guarded by tenant/project/version/deployment labels. Redis carries one short-lived shared gateway request counter; Web owns the short sample window, not PostgreSQL/Redis time-series. Docker IO is bounded to 2s and counter IO to 0.2s. Production range queries remain Prometheus-backed.

- **Local Development:** Transient real-time logs stream into Redis lists (`training_logs:{job_id}`, `build_logs:{build_id}`, `drift_logs:{run_id}`). Web frontend polls using cursor tokens.
- **Production Kubernetes:** Task logs are collected by Alloy into Grafana Loki (7-day retention). Control Plane acts as an authorized proxy: generates signed task-bound cursors to prevent cross-tenant LogQL injection.

## Training workspace changes

Use [training-workspaces.md](training-workspaces.md) when changing projectless jobs, assignment or deletion. Draft mutations and run admission serialize on TrainingWorkspace; each TrainingJob owns one immutable execution snapshot. Workspace deletion locks its jobs before checking Build/Version references. Operations involving Project/job coordinate Project before job. Nullable joined Project rows cannot be locked by PostgreSQL select_for_update without narrowing the lock with of=("self",). Test these paths on PostgreSQL as well as isolated fixtures.

## Account avatar

CustomUser.avatar is the only current-avatar reference; there is no UserAvatar history model or history/select API. Keep GET/PUT /api/auth/profile/ and the avatar/remove_avatar payload. Profile, registration and first-account OAuth import use services/avatars.py: validate a real image up to 5 MiB, upload a new UUID key outside transactions, lock the account to swap the reference, and delete only the superseded object after commit. Cleanup tasks retry up to five times and must skip a currently referenced or out-of-tenant key. Never overwrite storage keys or remove an entire avatar prefix. UserSerializer exposes avatar read-only to avoid writing the same upload twice. Later OAuth sign-ins neither replace custom images nor restore removed images.

Removing the historical avatar table edits identity's initial migration and requires a user-managed development database/storage reset; do not apply it as a data-preserving production migration.
