# Local Docker Compose

The Compose topology includes PostgreSQL/schema initialization, Control Plane, Celery worker, model-server, ML/DL base images, Traefik, model-packager/Evidently/training-runner utility images, Redpanda/init, consumer, Redis and MLflow. Local does not deploy Prometheus/cAdvisor. Check live Compose before assuming ancillary dashboards exist.

- Internal DNS uses Compose service names on `mlops_paas_network`.
- Browser URLs use published localhost ports; containers must not call browser-only localhost addresses.
- Docker execution builds local images and starts runtime containers named from Build/deployment/job UUIDs.
- Docker socket access is privileged infrastructure; limit it to trusted orchestration services.
- Named volumes retain database/broker/cache state across ordinary restarts.
- Training workspace migrations preserve existing data and backfill job ownership; do not reset application DB, volumes or brokers. Fixed container names prevent side-by-side stacks by project-name alone.
- Local runtime metrics use bounded Docker SDK stats for CPU/RAM and a shared transient gateway request counter in Redis (TTL 300s). Web polls every 5s while foregrounded, keeps at most 60 points/5 minutes in page memory, and resets on leave/refresh/deployment change. Never accept client container IDs; verify all runtime ownership labels. Missing stats/counter resets are not zero; production Prometheus remains unchanged.
- Use `docs/dev/web-workflow-local.md` for bootstrap and runtime smoke. Static tests/mock API integration are not a completed Docker/S3/Evidently/training end-to-end test.

Before changing a port or service name, search Compose, `.env.example`, Control Plane settings, Traefik configuration, frontend environment, and tests.

Use `docker compose config`, `docker ps -a`, service health checks, and scoped `docker logs`. Do not delete volumes or images unless explicitly authorized.

P1 training/drift use PostgreSQL leases and Beat recovery with
`TRAINING_EXECUTION_WATCH_ENABLED=true, DRIFT_EXECUTION_WATCH_ENABLED=true` in Compose. Separate Control Plane readiness from
Traefik ping, gateway `http://localhost:5001/health/ready` and Kafka/consumer ingestion checks. Port 5002 routes inference and does not expose gateway readiness. Inference
uses a cookie-free Bearer client. Training applies CPU/RAM/optional GPU and a runner
wall-clock deadline. See `docs/dev/p1-execution-recovery.md` for additive migrations,
ownership inventory, scoped Docker/S3 acceptance and offline Argo staging smoke.

## Training workspace rollout

Apply additive training migrations, rebuild the training-runner image, and restart Control Plane/Celery worker/Beat to load code changes. Wait for /health/ready before smoke runs. Docker Input helpers run asynchronously with per-job labeled volumes; the main runtime mounts Input read-only and cleanup must verify ownership before removal. Keep CPU/RAM reservations until runtime cleanup is confirmed.

TRAINING_SECRET_ENCRYPTION_KEY is optional and backend-only: absent key makes Secrets unavailable without disabling jobs that use no Secrets. Do not print real keys. The disposable integration script services/control-plane/scripts/verify_training_workspace.py exercises actual Docker/S3 execution, model upload, assignment and storage retention; clean up only its test tenant and confirmed runtimes.
