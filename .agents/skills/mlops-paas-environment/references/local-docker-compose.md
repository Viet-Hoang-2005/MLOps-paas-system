# Local Docker Compose

The Compose topology includes PostgreSQL/schema initialization, Control Plane, Celery worker, model-server, ML/DL base images, Traefik, model-packager/Evidently/training-runner utility images, Redpanda/init, consumer, Redis and MLflow. Local does not deploy Prometheus/cAdvisor. Check live Compose before assuming ancillary dashboards exist.

- Internal DNS uses Compose service names on `mlops_paas_network`.
- Browser URLs use published localhost ports; containers must not call browser-only localhost addresses.
- Docker execution builds local images and starts runtime containers named from Build/deployment/job UUIDs.
- Docker socket access is privileged infrastructure; limit it to trusted orchestration services.
- Named volumes retain database/broker/cache state across ordinary restarts.
- Local workflow refactor requires a clean application DB; no Preview/Running backfill. `POSTGRES_VOLUME_NAME` can choose a fresh volume while preserving the old one; never reset volume/broker automatically. Fixed container names prevent side-by-side stacks by project-name alone.
- Local runtime metrics use bounded Docker SDK stats for CPU/RAM and a shared transient gateway request counter in Redis (TTL 300s). Web polls every 5s while foregrounded, keeps at most 60 points/5 minutes in page memory, and resets on leave/refresh/deployment change. Never accept client container IDs; verify all runtime ownership labels. Missing stats/counter resets are not zero; production Prometheus remains unchanged.
- Use `docs/dev/web-workflow-local.md` for bootstrap and runtime smoke. Static tests/mock API integration are not a completed Docker/S3/Evidently/training end-to-end test.

Before changing a port or service name, search Compose, `.env.example`, Control Plane settings, Traefik configuration, frontend environment, and tests.

Use `docker compose config`, `docker ps -a`, service health checks, and scoped `docker logs`. Do not delete volumes or images unless explicitly authorized.
