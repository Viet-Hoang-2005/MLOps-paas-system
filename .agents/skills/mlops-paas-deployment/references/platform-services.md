# Platform services

Service/domain child Applications cover PostgreSQL/CloudNativePG, Redis,
Redpanda, MLflow, Harbor, monitoring, Cloudflare, storage, health, workflows,
and application workloads. The root Application owns only GitOps control
resources. Karpenter NodeClass/NodePool are not GitOps-owned.

Operators/controllers may be installed first by Ansible:

- External Secrets.
- CloudNativePG.
- KEDA.
- Argo Workflows.
- Monitoring stack.
- Argo CD.

Kubeflow Training Operator, Karpenter CRD/controller, NFD and GPU Operator are
Argo CD child Applications. Ansible still supplies cluster-specific Karpenter
runtime settings and capacity resources. CPU capacity comes before GPU capacity.

Confirm CRDs/controllers exist before applying custom resources. Harbor is reconciled through its GitOps directory once referenced by root. Cloudflare exposes selected low-bandwidth/private UIs; do not assume it is suitable for large model uploads or registry pushes.

KEDA/HPA scale application workloads; Karpenter scales nodes only where the underlying cloud integration exists. External VM K3s deployments require an alternate capacity plan.
