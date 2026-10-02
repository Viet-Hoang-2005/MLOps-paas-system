---
name: mlops-paas-deployment
description: Implement or review K3s GitOps resources, Kustomize overlays, Argo CD, Argo Events/Workflows, Kubeflow jobs, platform services, autoscaling, CI/CD promotion, rollback, and operational validation. Use for changes under k8s/ or cluster deployment workflows.
---

# MLOps PaaS Deployment & GitOps

Use this skill to implement, modify, review, or troubleshoot K3s GitOps declarations (`k8s/`), Kustomize overlays, Argo CD applications, operators, platform services, and runtime execution workflows.

Never embed passwords, tokens, private keys, real environment values, or SSH credentials in skills, manifests, or outputs.

## Workflow

1. Inspect root Kustomization (`k8s/kustomization.yaml`), child Applications (`k8s/gitops/production/applications/`), base manifests (`k8s/apps/base/`), and overlays (`k8s/apps/overlays/production/`).
2. Read [gitops-and-kustomize.md](references/gitops-and-kustomize.md) for sync waves, and [platform-services.md](references/platform-services.md) for operators.
3. Determine resource ownership: GitOps (Argo CD), Ansible bootstrap, Terraform IaaS, or runtime workflow.
4. Render manifests locally (`kubectl kustomize`) before committing or applying to the cluster.
5. Respect Sync Wave ordering (`-50` to `20`) to prevent race conditions during cluster synchronization.
6. Preserve namespace segregation (`mlops-system`, `mlops-control-plane`, `mlops-model-runtimes`, etc.).
7. Maintain Kyverno image verification policies and Redis HA quorum requirements.

## 5 System Planes & Sync Waves

- **Plane 1: Cluster Plane (Sync Wave `-50`):** Namespaces, core CRDs, PriorityClasses.
- **Plane 2: Addons Plane (Sync Waves `-40` to `-31`):** Ingress (Traefik), CloudNativePG, Redis Operator, Redpanda Operator, External Secrets Operator (ESO), Loki, Alloy, Prometheus Stack, Harbor.
- **Plane 3: Platform Plane (Sync Waves `-30` to `-21`):** ClusterSecretStores, Cert-Manager, Kyverno Policy Engine.
- **Plane 4: Execution Plane (Sync Waves `-20` to `-11`):** Argo Workflows Controller, Argo Events EventSource/Sensors, Kubeflow Training Operator, Karpenter Autoscaler, KEDA.
- **Plane 5: Workloads Plane (Sync Waves `0` to `20`):** Database migration Jobs, Control Plane, Celery Worker, Model Server Gateway, Consumer Worker, MLflow Tracking Server, Web Dashboard.

## Validation

Execute offline validation suites to verify manifests and contracts before pushing to Git:
```bash
pytest k8s/validate/tests/ -v
```
To test rendering of specific overlays:
```bash
kubectl kustomize k8s/apps/overlays/production
kubectl kustomize k8s/gitops/production/applications
```
