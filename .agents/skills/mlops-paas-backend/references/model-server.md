# Model Server

Production metrics: the Uvicorn parent creates a fresh process-metric directory before importing the app/spawning workers. `/metrics` builds a fresh MultiProcessCollector registry per scrape, aggregating counters/histograms across workers in this pod. Worker restarts must not clear files; parent restarts reset counters. Each production Pod has its own emptyDir. CPU/RAM comes from cAdvisor joined to explicit kube-state-metrics Pod identity labels (tenant/project/version/deployment); never Docker-style labels on Kubernetes. Existing runtimes need redeployment to receive these Pod labels. Local Web realtime still uses Docker SDK and the short-lived Redis request counter.

The Model Server (`services/model-server/`) is the centralized, trusted inference gateway. Worker runtimes (`machine-learning-serving`, `deep-learning-serving`) reside in protected internal networks and do not implement authentication.

## Core Responsibilities

1. **Central Ingress:** Single entrypoint for client prediction traffic via `POST /models/{version_id}/predict` and `GET /models/{version_id}/health`.
2. **Multi-Modal Authentication:**
   - Evaluates model project access mode (`public`, `protected`, `private`).
   - Verifies Bearer JWTs (`RS256`) against Control Plane's JWKS endpoint (`/api/auth/.well-known/jwks.json`), caching public keys in Redis.
   - Validates machine-to-machine Project API Keys (`X-API-Key`) hashed with SHA-256 against Redis cache or PostgreSQL.
3. **Dynamic Multi-Environment Routing:**
   - *Docker Compose:* Resolves internal container URLs (e.g. `http://machine-learning-serving:5001/predict`).
   - *Kubernetes K3s:* Resolves CoreDNS FQDNs in namespace `mlops-model-runtimes` (e.g. `http://<deployment>.<namespace>.svc.cluster.local:5000/predict`).
4. **Asynchronous Production Telemetry:**
   - Proxies input features to the target worker using `httpx.AsyncClient`.
   - Returns prediction results to the client immediately.
   - Emits an inference telemetry event to Redpanda Kafka topic `mlops_paas_production_data` in `BackgroundTasks`.
   - Kafka producer failure is logged and recorded in Prometheus metrics, but must NEVER fail the client's inference response.
5. **Observability:** Exposes Prometheus metrics (request counters, latency histograms categorized by tenant, project, and status).
