# Local Docker Compose

Use [docker-compose.yml](../../../../docker-compose.yml) for service names, profiles, networks, ports and volumes. The local stack includes PostgreSQL, Redpanda, Redis cache and queue, Control Plane, Celery worker/Beat, Model Server, Consumer and on-demand runtime images. Use each caller's network and actual settings when checking its dependencies.

- Containers use Compose DNS names; host/browser clients use the published ports. In a container, localhost refers to that container. Check both the Kafka bootstrap address and advertised listener from the consumer's network.
- Check service state with `docker compose ps -a` and scoped logs with `docker compose logs --tail 100 <service>`. Use `docker compose config --services` for discovery without printing the resolved environment.
- Identify whether a fix needs a process restart, service recreation for new env, or a rebuild for installed dependencies. Keep volumes and unrelated services intact during ordinary troubleshooting.
- Training preparation runs in Celery before Docker dispatch; see [workspace lifecycle](../../../../docs/dev/training-workspaces.md). After dispatch, inspect the labeled Input helper, per-job volume and main container separately. Use job and tenant labels before any scoped cleanup.
- Verify dependency changes against the actual Dockerfile and installed Python, using [backend testing](../../mlops-paas-backend/references/testing.md).
