# Production runtime

- K3s hosts trusted platform services.
- Argo Events/Workflows execute build, deployment, deletion, drift, and training orchestration.
- Kubeflow Training Operator creates training resources in `user-jobs`.
- Harbor stores user images; S3 stores artifacts and reports.
- External Secrets materializes Secrets Manager data for trusted namespaces.
- Production configuration selects `argo` execution globally or per component.

Tenant build/training/model workloads are untrusted. They receive IDs, scoped callback capability, and presigned URLs—not shared production secrets.

Operators such as External Secrets, CloudNativePG, KEDA, Argo Workflows, Kubeflow Training Operator, Karpenter, monitoring, and Argo CD may be installed by Ansible. Confirm install ownership before adding duplicate GitOps resources.
