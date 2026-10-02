# Control Plane

The Django Control Plane is a domain-oriented modular monolith (`services/control-plane/`). It owns identity, authorization, relational source of truth (PostgreSQL schema `control_plane`), presigned storage URL generation, task dispatch, and trusted callbacks.

## App Ownership

1. **`auth`:** CustomUser, user profile avatars, RS256 JWT issuance, JWKS endpoint (`/api/auth/.well-known/jwks.json`), OAuth2 (Google/GitHub), 2FA/TOTP.
2. **`access`:** Project-scoped API keys (`ApiKey`) hashed with SHA-256 for machine-to-machine authentication.
3. **`catalog`:** Mutable workspaces (`ModelProject`), dataset snapshots, feature views, async project deletion.
4. **`registry`:** Immutable registered versions (`ModelVersion`), artifacts, metrics, insights, dynamic aliases (`champion`/`challenger`).
5. **`training`:** Training jobs (`TrainingJob`), short-lived Capability Tokens, Presigned S3 URLs, resource quotas, graceful cancellation.
6. **`deployment`:** Container packaging builds (`Build`), model serving deployments (`Deployment`), router endpoints (`Endpoint`), execution task dispatch.
7. **`drift`:** Drift monitors (`DriftMonitor`), scheduled and event-driven drift runs (`DriftRun`), report access, threshold configuration.
8. **`ct` (Continuous Training):** Retraining policies, automated retraining triggers (`RetrainingTrigger`), pipeline orchestration upon drift signals.
9. **`production`:** Production inference records (`ProductionPredictionRecord`), telemetry datasets, schema coordination with Consumer worker.
10. **`observability`:** Health endpoints (`/health/live`, `/health/ready`), Prometheus metrics (`/health/metrics`), transactional event outbox, runtime log proxy.

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

## Runtime Logs Architecture

- **Local Development:** Transient real-time logs stream into Redis lists (`training_logs:{job_id}`, `build_logs:{build_id}`, `drift_logs:{run_id}`). Web frontend polls using cursor tokens.
- **Production Kubernetes:** Task logs are collected by Alloy into Grafana Loki (7-day retention). Control Plane acts as an authorized proxy: generates signed task-bound cursors to prevent cross-tenant LogQL injection.
