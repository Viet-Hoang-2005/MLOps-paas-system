# Production runtime

- K3s hosts trusted platform services.
- Argo Events/Workflows execute build, deployment, deletion, drift, and training orchestration.
- Kubeflow Training Operator creates training resources in `mlops-paas-training`.
- Harbor stores user images; S3 stores artifacts and reports.
- External Secrets materializes Secrets Manager data for trusted namespaces.
- Production configuration selects `argo` execution globally or per component.

Tenant build/training/model workloads are untrusted. They receive IDs, scoped callback capability, and presigned URLs—not shared production secrets.

Operators such as External Secrets, CloudNativePG, KEDA, Argo Workflows, Kubeflow Training Operator, Karpenter, monitoring, and Argo CD may be installed by Ansible. Confirm install ownership before adding duplicate GitOps resources.

Workspace training uses a trusted init container and a read-only Input mount in the main container. Promote the same runner image for both stages before rollout. TRAINING_SECRET_ENCRYPTION_KEY is delivered by the training ExternalSecret only to trusted Control Plane/worker services, never to tenant pods. See the deployment Argo reference and docs/dev/training-model-output.md.
