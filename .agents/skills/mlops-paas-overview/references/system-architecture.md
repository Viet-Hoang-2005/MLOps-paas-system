# System architecture

| Boundary | Owner and handoff |
| --- | --- |
| Dashboard | React routes identify the selected project, workspace, job or run. Feature API clients call the Control Plane. |
| Control Plane | Django owns lifecycle operations and records them in PostgreSQL. Celery executes background work. External outcomes return through trusted callbacks or reconciliation. |
| Local execution | Control Plane adapters dispatch through Docker SDK. Training prepares a read-only Input volume with a per-job helper. Compose defines the local network and backing services. |
| Production execution | Argo Events dispatches to Git-managed Argo Workflows. Training creates a Kubeflow Trainer v2 `TrainJob` with a trusted Input init container. Karpenter supplies eligible node capacity. |
| Serving and ingestion | Model Server authorizes and routes requests to the version's worker. Prediction events flow through Redpanda to Consumer and PostgreSQL. |
| Drift and retraining | Evidently compares reference and production data. Control Plane records drift outcomes and applies configured retraining policy. |
| Storage | PostgreSQL owns lifecycle state and production records; S3 stores object payloads; Harbor stores OCI images; Redis handles caching, transient log transport and Celery coordination. |
| Observability | Inspect the configured backend for the resource: local transient log streams, production Alloy/Loki, and Prometheus where deployed. Log output and lifecycle status have separate owners. |

Trace changes to dispatch or result handling through the domain operation, transaction boundary, selected execution adapter, runtime and result handler. Read [core lifecycles](lifecycles.md) for concrete entry points.
