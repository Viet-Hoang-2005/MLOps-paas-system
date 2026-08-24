# Model server

model-server is the trusted inference gateway; version workers are not auth gateways.

- Resolve model/version, tenant ownership, access mode, deployment, and endpoint from PostgreSQL/registry cache.
- Authenticate public access, API keys, or JWT/JWKS as required.
- Route only to the worker for the requested `MODEL_VERSION_ID`.
- Proxy predict/health responses and preserve status/error semantics.
- Publish a production event only after successful inference.
- Event payload includes UUID, tenant, project, version, features, prediction, and optional confidence/engine.
- Producer failure must be observable but must not turn a successful prediction into an inference failure.
- Initialize Redis/Kafka clients in lifespan/factories, not at import time.

Worker URLs differ between Docker and Kubernetes; missing runtime/deployment is a service-unavailable condition.
