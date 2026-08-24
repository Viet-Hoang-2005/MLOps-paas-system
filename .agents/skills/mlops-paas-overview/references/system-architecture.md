# System architecture

## Planes

- **Control plane:** Django API and Celery coordinate projects, jobs, builds, versions, deployments, drift runs, and cleanup.
- **Data plane:** model-server authenticates inference, proxies a version-specific worker, and publishes successful inference events.
- **Execution plane:** Docker locally; Argo Workflows, Argo Events, and Kubeflow Training Operator in production.
- **Storage plane:** PostgreSQL for relational lifecycle state, S3 for immutable/mutable object bundles, Harbor or Docker for images, Redis for transient state.
- **Observability plane:** Prometheus/Grafana, application logs, Redis runtime streams, events, and health endpoints.

## State ownership

PostgreSQL owns lifecycle status and relationships. S3 owns artifacts, source/data snapshots, training outputs, and drift reports. Image registries own image manifests and layers. Redis must never become the sole source of completed lifecycle state.

## Identifiers

- `tenant_uuid`: isolation and public inference routing.
- `project_uuid`: model project and latest metadata.
- `model_version_uuid`: immutable registered version.
- `build_uuid`: one image build attempt and runtime log stream.
- `deployment_uuid`: one deployment attempt and runtime name.
- `training_job_uuid`: one immutable training execution.
- `monitor_uuid`: drift configuration.
- `run_uuid`: one drift execution/report.

## Orchestration boundary

HTTP endpoints validate and authorize. Services mutate state inside transactions. Side effects are dispatched after commit through Celery and backend factories. Execution backends report through authenticated, idempotent callbacks.
