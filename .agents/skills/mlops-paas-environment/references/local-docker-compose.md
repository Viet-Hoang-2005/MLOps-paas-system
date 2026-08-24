# Local Docker Compose

The Compose topology includes PostgreSQL/schema initialization, pgAdmin, Control Plane, Celery worker, model-server, ML/DL base images, Traefik, model-packager and Evidently utility containers, Redpanda/init/console, consumer, Redis, and MLflow.

- Internal DNS uses Compose service names on `mlops_paas_network`.
- Browser URLs use published localhost ports; containers must not call browser-only localhost addresses.
- Docker execution builds local images and starts runtime containers named from Build/deployment/job UUIDs.
- Docker socket access is privileged infrastructure; limit it to trusted orchestration services.
- Named volumes retain database/broker/cache state across ordinary restarts.

Before changing a port or service name, search Compose, `.env.example`, Control Plane settings, Traefik configuration, frontend environment, and tests.

Use `docker compose config`, `docker ps -a`, service health checks, and scoped `docker logs`. Do not delete volumes or images unless explicitly authorized.
