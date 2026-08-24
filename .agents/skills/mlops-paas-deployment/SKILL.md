---
name: mlops-paas-deployment
description: Implement or review K3s GitOps resources, Kustomize overlays, Argo CD, Argo Events/Workflows, Kubeflow jobs, platform services, autoscaling, CI/CD promotion, rollback, and operational validation. Use for changes under k8s/ or cluster deployment workflows.
---

# MLOps PaaS deployment

## Workflow

1. Inspect the root Kustomization, relevant base/overlay, Argo application, Ansible add-on ownership, and CI/CD workflow.
2. Read [gitops-and-kustomize.md](references/gitops-and-kustomize.md), then the affected workload/platform/execution reference.
3. Identify whether GitOps, Ansible, Terraform, or a runtime workflow owns the resource.
4. Render manifests before editing live resources; avoid duplicate operator ownership.
5. Preserve namespace, service-account, security, and callback contracts.
6. Record existing topology gaps rather than assuming every manifest is reconciled.
7. Preserve user changes and avoid unrelated manifest formatting/refactors.
8. Update this skill when deployment ownership or topology changes.

Load `$mlops-paas-security` for exposure, credentials, workload isolation, IAM, or webhooks; load `$mlops-paas-architecture` for cluster/bootstrap changes.

For cross-service deployment changes also load `$mlops-paas-overview`. Treat rendered manifests, workflows, tests, and live ownership configuration as more authoritative than README or architecture prose; reconcile conflicts explicitly. Never embed passwords, tokens, private keys, real environment values, or SSH credentials.

## Validation

Render the affected Kustomization, run schema/dry-run checks where available, and inspect the final namespace, image, secret/config references, probes, and service selectors.
