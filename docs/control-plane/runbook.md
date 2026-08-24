# Control Plane Runbook

## Local Start

```bash
docker compose config
docker compose up --build control-plane control-plane-worker model-server traefik
```

The local model gateway is `http://localhost:5002`. PostgreSQL, Redis, S3
credentials (or an S3-compatible endpoint), and the Docker socket must be
available to the control-plane web and worker containers.

## Fresh Schema Cutover

This release intentionally does not preserve the old control-plane schema.
Do not use `docker compose down -v`; MLflow and unrelated PostgreSQL schemas must
remain intact.

1. Stop web and worker traffic.
2. Back up anything that must be retained.
3. Set `ALLOW_CONTROL_PLANE_RESET=YES` only for the reset command.
4. Run:

```bash
python manage.py reset_control_plane_schema --confirm RESET-CONTROL-PLANE
python manage.py migrate
python manage.py bootstrap_control_plane
```

The reset command refuses SQLite and drops only the configured PostgreSQL
`DB_SCHEMA` (normally `control_plane`). It does not touch the MLflow schema.

## Managed Resource Cleanup

Preview:

```bash
python manage.py cleanup_legacy_resources
```

Execute only during the destructive hard cut:

```bash
ALLOW_RESOURCE_CLEANUP=YES python manage.py cleanup_legacy_resources \
  --execute --confirm DELETE-LEGACY-RESOURCES
```

Add `--include-harbor` only when the configured Harbor project may be fully
cleared. The command deletes `users/` from the configured artifact bucket and
control-plane-managed Docker runtime containers. Kubernetes resources must be
removed through the deployment workflow or the environment's GitOps process.

## Verification

```bash
python manage.py check --deploy --settings=config.settings.production
python manage.py makemigrations --check --dry-run --settings=config.settings.test
python -m pytest
curl -f http://localhost:8000/health/live
curl -f http://localhost:8000/health/ready
```

Then smoke test: project upload, workspace edit, training, version registration,
build, deployment, prediction, drift run, stop, and cleanup.

Failed build/training/drift containers are retained for debugging. Successful
short-lived containers are removed. Endpoint containers remain until stopped.
