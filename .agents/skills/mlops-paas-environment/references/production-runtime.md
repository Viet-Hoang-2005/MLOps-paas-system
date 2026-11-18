# Production runtime

- Start at the owning Application and rendered workload. Match its image and config to the deployed Git revision when live diagnostics are in scope.
- Use the production settings, ConfigMap, Secret references and workload env to confirm which adapter or endpoint is active. Inspect variable names and resource readiness without printing credentials.
- The [Argo execution reference](../../mlops-paas-deployment/references/argo-execution.md) maps WorkflowTemplates, logs and callbacks. Kubeflow Trainer v2 creates training workloads in `mlops-paas-training`; see the [Trainer contract](../../../../docs/dev/trainer-v2.md).
- Ansible bootstraps K3s and Argo CD. Check GitOps Application ownership before changing controllers, backing services or workload resources.
- Image promotion for Training Runner must keep trusted init and main images aligned. The encryption key belongs to the trusted backend; tenant processes receive scoped runtime configuration.
