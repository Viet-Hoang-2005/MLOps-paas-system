---
name: mlops-paas-deployment
description: Change or diagnose production K3s GitOps, Argo workflows, workload rollouts, autoscaling, and CI/CD image promotion.
---

# MLOps PaaS Deployment

Start at the owning Application or WorkflowTemplate. Trace its sources, patches and image references to the rendered resource. For production diagnosis, confirm the deployed revision and runtime status when live access is in scope.

- [GitOps and Kustomize](references/gitops-and-kustomize.md) locates Applications, projects, overlays and promotion boundaries.
- [Argo execution](references/argo-execution.md) traces events, build/training/drift/deployment workflows, callbacks and log sources.
- [Platform services](references/platform-services.md) and [application workloads](references/application-workloads.md) identify placement, dependencies and health checks.
- [Operations and validation](references/operations-and-validation.md) covers offline rendering, CI checks and live acceptance.

Validate the smallest affected rendered path and contract under [k8s/verify/validate](../../../k8s/verify/validate). Compare the result with [.github/workflows/ci.yml](../../../.github/workflows/ci.yml). For promotion changes, also check the image update in [CD](../../../.github/workflows/cd.yml). GitOps sync and live smoke tests require the corresponding operational scope.
