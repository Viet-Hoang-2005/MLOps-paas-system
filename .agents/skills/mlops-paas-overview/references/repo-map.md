# Repository Map

| Path | Ownership & Responsibility |
| --- | --- |
| `web/` | React/Vite frontend dashboard, route coordinators, React Query hooks, design tokens, and i18n |
| `services/control-plane/` | Django modular monolith API, 10 domain apps, lifecycle orchestration, Celery workers, execution factories |
| `services/consumer/` | High-throughput Redpanda Kafka worker, micro-batch persistence, transactional outbox for drift signals |
| `services/model-server/` | Centralized inference gateway, JWT/JWKS & API key authentication, dynamic worker routing, telemetry events |
| `services/machine-learning-serving/` | Stateless FastAPI serving worker for classical ML models (Scikit-Learn, XGBoost, LightGBM) |
| `services/deep-learning-serving/` | Stateless BentoML serving worker for deep learning models (PyTorch, TensorFlow, Keras) |
| `services/model-packager/` | Model artifact packaging, Dockerfile generation, Docker SDK (local) & Kaniko (production) image builds |
| `services/training-runner/` | Untrusted training sandbox execution, presigned URL I/O, `METRIC_JSON` protocol, output bundling |
| `services/evidently/` | Standalone statistical drift runner, K-S / Chi-square analysis, HTML/JSON/summary reports, CT trigger |
| `services/mlflow/` | MLflow tracking server container setup |
| `infra/` | Terraform AWS infrastructure (VPC, EC2, S3, IAM, ALB, DNS, Secrets Manager, Karpenter, S3-only mode) |
| `ansible/` | Automated Ubuntu OS preparation, K3s embedded etcd bootstrap, Helm CLI, Argo CD GitOps core handoff |
| `k8s/` | Declarative GitOps resources, 5 System Planes (-50 to 20), Kustomize overlays, Argo Workflows/Events |
| `docs/` | Technical specifications, backend layout rules, runtime logs architecture, continuous training designs |

## Control Plane 10 Domain Apps

1. **`auth`:** CustomUser, identity, profile avatars, JWT issuance (RS256 with `/api/auth/.well-known/jwks.json`), OAuth2 (Google/GitHub), 2FA/TOTP.
2. **`access`:** Project-scoped API keys (`ApiKey`) hashed with SHA-256 for machine-to-machine inference authentication.
3. **`catalog`:** Mutable model projects (`ModelProject`), workspace source/data assets, feature views, async deletion.
4. **`registry`:** Immutable registered model versions (`ModelVersion`), artifacts, metrics, explainability insights, dynamic aliases (`champion`/`challenger`).
5. **`training`:** Training jobs (`TrainingJob`), short-lived Capability Tokens, Presigned S3 URLs, resource quotas, graceful cancellation.
6. **`deployment`:** Container image builds (`Build`), model deployments (`Deployment`), router endpoints (`Endpoint`), multi-backend execution.
7. **`drift`:** Drift monitors (`DriftMonitor`), scheduled/event-driven drift runs (`DriftRun`), report URLs, threshold management.
8. **`ct` (Continuous Training):** Retraining policies, automated retraining triggers (`RetrainingTrigger`), pipeline orchestration upon drift signals.
9. **`production`:** Production inference records (`ProductionPredictionRecord`), telemetry datasets, schema coordination with Consumer.
10. **`observability`:** Health endpoints (`/health/live`, `/health/ready`), Prometheus metrics (`/health/metrics`), transactional event outbox, runtime log proxy.

## Source Precedence Rules

1. Executable source code and live PostgreSQL database migrations.
2. Automated test suites asserting current contracts (`pytest`, `k8s/validate/tests/`).
3. Kubernetes manifests, Terraform modules, Ansible roles, Docker Compose, and CI/CD pipelines.
4. Focused service documentation (`services/*/README.md`, `infra/README.md`, `ansible/README.md`, `k8s/README.md`, `ARCHITECTURE.md`).
5. Supporting notes and example environment files (`.env.example`).
