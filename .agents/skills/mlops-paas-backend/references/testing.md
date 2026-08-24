# Backend testing

Use pytest for every service. Common tooling is in `services/requirements-test.txt`; service-specific test dependencies may be local.

From a service directory:

```bash
python -m pytest tests --cov=src --cov-report=term-missing --cov-report=xml --cov-fail-under=70
```

Control Plane test paths may follow its Django source layout; run the smallest affected app set first.

## Isolation rules

- No real PostgreSQL, Redis, Redpanda, MLflow, Docker, S3, Harbor, Kubernetes, or Control Plane calls in unit tests.
- Use pytest fixtures, monkeypatch, `tmp_path`, `Mock`/`AsyncMock`, and FastAPI TestClient/httpx.
- Reset environment, caches, and global clients between tests.
- Cover success, validation, timeout, retry, non-2xx, callback replay, tenant isolation, and cleanup.
- Keep import-time behavior side-effect free.

CI runs services as an isolated matrix and enforces at least 70% line coverage per service.
