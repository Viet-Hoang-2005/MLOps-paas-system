# Backend service layout

The seven application services outside Control Plane use a thin process entrypoint. A service's
`src/main.py` may configure process lifecycle, export the framework object, and delegate to an
application module; it must not own queries, HTTP clients, retries, or data transformations.

| Service | Entrypoint | Responsibility modules |
|---|---|---|
| Consumer | `src.main` | `kafka_runtime`, `batching`, `models`, `database`, `drift_outbox` |
| Model Server | `src.main:app` | `api`, `auth`, `routing`, `events`, `inference`, `schemas` |
| ML Serving | `src.main:app` | `api`, `inference`, `loading`, `schemas` |
| DL Serving | `src.main:DeepLearningModelService` | `service`, `inference`, `loading` |
| Model Packager | `src.main` | `tasks`, `config`, `io`, `image_build`, `core` |
| Evidently | `src.main` | `application`, `config`, `data`, `analysis`, `reporting` |
| Training Runner | `src.main` | `application`, `config`, `io`, `metadata`, `resources`, `execution` |

All code and container commands target `src.main`. Rollback uses the previous immutable image or
Git revision; legacy `index.py`, `cli.py`, and `runner.py` entrypoints are not retained.

Each service owns its modules and dependencies. There is no cross-service Python package. Business
modules receive mutable clients or runtime callbacks through parameters where practical so imports
remain free of network and database connections and unit tests can replace those dependencies.

See [production-data-contract.md](production-data-contract.md) for the Consumer-owned telemetry and
continuous-training dataset boundary.
