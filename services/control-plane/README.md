# Django Control Plane

The control plane is a domain-oriented Django modular monolith. It owns identity,
model workspaces, immutable registry versions, training, builds, deployments,
drift monitoring, API keys, audit events, and asynchronous orchestration.

## Layout

```text
control-plane/
|-- manage.py
|-- pyproject.toml
|-- requirements.txt
`-- src/
    |-- config/                 # Settings, root URLs, ASGI/WSGI, Celery
    |-- common/                 # API policy, middleware, logging, metrics
    |-- infrastructure/         # S3, Docker, Argo, Harbor, HTTP, Redpanda
    `-- apps/
        |-- auth/               # CustomUser, profile, JWT, OAuth, OTP
        |-- access/             # Project-scoped API keys
        |-- catalog/            # ModelProject and mutable workspace assets
        |-- registry/           # Immutable versions, artifacts, aliases
        |-- training/           # Jobs, events, outputs, snapshots
        |-- deployment/         # Build, Deployment, Endpoint
        |-- drift/              # DriftMonitor and DriftRun
        `-- observability/      # Health, metrics, outbox, model telemetry
```

Each domain exposes HTTP endpoints through `api/`, writes through `services/`,
and reads through tenant-scoped `selectors.py`. API modules must not call Docker,
S3, Argo, Harbor, Redis, or external HTTP clients directly.

## Local Development

From the repository root:

```bash
docker compose up --build control-plane celery-worker
```

Without Docker:

```bash
cd services/control-plane
python -m pip install -r requirements.txt
python manage.py migrate --settings=config.settings.local
python manage.py runserver --settings=config.settings.local
celery -A config worker
```

Quality gates:

```bash
python -m ruff check .
python -m pytest
python manage.py check --settings=config.settings.test
python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

Health endpoints are `/health/live`, `/health/ready`, and `/health/metrics`.
The public API intentionally has no version prefix. See
[`docs/control-plane/api-catalog.md`](../../docs/control-plane/api-catalog.md).

## Cutover

This schema is a hard cut and does not migrate legacy control-plane data. The
guarded reset and cleanup procedure is documented in
[`docs/control-plane/runbook.md`](../../docs/control-plane/runbook.md). Never run
the cleanup commands against an environment that must preserve artifacts.
