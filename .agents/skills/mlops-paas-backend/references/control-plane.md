# Control Plane

The Django Control Plane owns lifecycle orchestration, authorization, relational truth, presigned storage access, task dispatch, and trusted callbacks.

## App ownership

- `auth`, `access`: identity, JWT/JWKS, OAuth, API keys.
- `catalog`: projects, workspace assets, deletion.
- `registry`: immutable versions/artifacts/metrics/insights.
- `training`: jobs, inputs/outputs, capabilities, cancellation.
- `deployment`: Builds, deployments, endpoints, execution tasks.
- `drift`: monitors, runs, production-data access, report URLs.

## Boundary pattern

```text
endpoint + serializer
→ tenant-scoped selector/service
→ transaction.atomic
→ transaction.on_commit
→ Celery task
→ execution backend factory
→ authenticated idempotent callback
```

Endpoints must not directly operate Docker, S3, Harbor, or Argo. Avoid service/task circular imports; place task imports at dispatch boundaries or move shared queries to selectors.

Use `select_for_update` for version allocation and concurrent terminal transitions. Late callbacks must not revive cancelled/deleting resources.
