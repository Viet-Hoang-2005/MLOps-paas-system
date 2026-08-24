# Trust boundaries

## Trusted

- Control Plane API and workers.
- model-server authentication gateway.
- database/storage/registry operators with scoped credentials.
- Argo/Kubernetes controllers and trusted lifecycle reporters.

## Untrusted

- Tenant-uploaded training source and dependencies.
- Dynamic model images/workers.
- Uploaded archives and model artifacts.
- Public/browser/API input.
- Runtime logs and callback payloads until authenticated and validated.

Untrusted workloads must not receive shared application secrets, JWT private keys, OAuth secrets, AWS credentials, production Redis, broad MLflow access, or node metadata access. Kubernetes target Secrets are scoped to the consuming workload: AWS may be a shared source, but a broad cross-workload target Secret is prohibited.

Dynamic model Deployments and Services run only in `mlops-model-runtimes`.
Trusted Control Plane, Consumer and Model Server workloads run in separate
`mlops-*` namespaces and use explicit FQDN service references across boundaries.

Platform images from `registry.mlops-nids-nt114.id.vn/mlops-paas/*` are trusted
only after Kyverno verifies a keyless Cosign signature from this repository's
GitHub Actions CD workflow on `main`. Images from tenant `user-images/*` remain
untrusted and are not covered by this policy until their isolated build path
has its own signer.

Karpenter-created training nodes may read only the dedicated K3s agent-token
secret during host bootstrap. The token value stays out of Git and Terraform
state; workload containers must not receive the node IAM credentials or token.

PostgreSQL terminal state is updated only by trusted orchestration/reporters. A tenant callback may report bounded progress but cannot authoritatively complete another resource.

Argo Events accepts execution requests only from the trusted Control Plane
worker using the dedicated `ARGO_EVENTS_WEBHOOK_TOKEN`; never reuse an
application callback secret. EventBus transport uses token authentication, and
execution NetworkPolicies restrict the EventSource and EventBus peer set.
Control Plane API/worker Pods do not mount Kubernetes API credentials. Sensor
and Workflow service accounts must retain function-specific minimum RBAC and
must never gain Secret CRUD or `pods/exec`.

When TLS terminates before Traefik, forwarded scheme and client headers are
trusted only from the explicit immediate proxy addresses observed at Traefik.
Do not trust an entire pod/VPC CIDR when narrower `/32` proxy hops are stable,
and never enable forwarded-header insecure mode on a public entrypoint.
