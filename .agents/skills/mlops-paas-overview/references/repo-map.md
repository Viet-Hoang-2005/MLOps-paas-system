# Repository map

| Path | Responsibility |
| --- | --- |
| `web/` | React/Vite dashboard. `src/app/router/AppRouter.tsx` wires the feature entry points. |
| `services/control-plane/` | Django API and lifecycle state. Start at `src/config/urls.py`, the owning app, then `src/infrastructure/execution/` when external work is involved. |
| `services/model-server/` | Inference gateway, request authorization, model worker routing and prediction telemetry. |
| `services/machine-learning-serving/`, `services/deep-learning-serving/` | Workers that load registered model artifacts and perform prediction. |
| `services/consumer/` | Redpanda ingestion, PostgreSQL persistence and outbox delivery. |
| `services/model-packager/` | Packages models and prepares build context. The selected backend determines who builds/pushes the image. |
| `services/training-runner/`, `services/evidently/` | Training process and output export; drift report generation, respectively. |
| `docker-compose.yml` | Local services, network and Docker execution dependencies. |
| `terraform/`, `ansible/`, `k8s/` | Cloud infrastructure, bootstrap and GitOps, respectively. |
| `.github/workflows/` | CI checks and image build/sign/promotion. |
| `models/`, `research/` | Example models and research artifacts, separate from deployed service code. |

Inside `services/control-plane/src/apps/`, start at `training` for workspaces/jobs, `deployment` for builds and deployments, `catalog` for mutable projects, `registry` for versions, and `production`/`drift`/`ct` for prediction records through retraining. Browser identity and machine access are owned by `auth` and `access`. Tracking routes live in `mlflow`; look in `observability` for health, metrics and log-facing integration. Confirm bindings in the actual URL configuration and the app before assuming a route name.
