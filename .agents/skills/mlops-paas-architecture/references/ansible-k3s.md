# Ansible K3s

Ansible owns host and cluster bootstrap through roles:

- `common`: OS packages, kernel/sysctl, users, prerequisites.
- `k3s_master`: first server/control-plane node and kubeconfig/token.
- `k3s_worker`: additional nodes joining the cluster.
- `helm`: pinned Helm client.
- `platform_core`: install pinned Argo CD and bootstrap the public root Application.
- `platform_training`: wait for root-owned training/capacity child Applications
  and run disposable smoke verification.
- `verify`: bootstrap and reconciled-platform assertions.

Use the rollout tags `preflight`, `bootstrap`, `platform-core`,
`platform-training`, and `verify`. Core defaults on; training, Karpenter, and GPU
capacity require explicit opt-in. K3s is configured through protected
`/etc/rancher/k3s/config.yaml` files and pinned by `INSTALL_K3S_VERSION`.

Dynamic inventory requires Terraform outputs for the server, workers, VPC and
EC2 key pair. Workers use ProxyJump through the server. Keep SSH keys outside
committed source; the WSL key must be `~/.ssh/aws_key` with mode `0600`.

Terraform owns AWS primitives, private K3s API DNS and agent-token secret
metadata. Ansible owns host/Argo CD bootstrap, adds the private DNS TLS SAN and
publishes the runtime token version. Argo CD owns pinned add-ons (AWS EBS CSI,
External Secrets, CloudNativePG, KEDA, Argo Workflows/Events, monitoring,
Kyverno and training controllers) and their separate cluster/platform instances
through the unified `mlops-paas-system` app-of-apps root. Karpenter
CRDs/controller are add-ons; EC2NodeClasses and NodePools are cluster
configuration.

Ansible also owns the bundled Traefik `HelmChartConfig`. Public TLS terminates
at the ALB, while K3s ServiceLB with `externalTrafficPolicy: Cluster` presents
the static worker Flannel gateway as Traefik's immediate peer. Trust only those
gateway `/32` addresses for forwarded headers; never use
`forwardedHeaders.insecure`. Revalidate the addresses whenever worker PodCIDRs
or ServiceLB traffic policy changes.

Traefik permits Kubernetes CRD cross-namespace references because the
Git-managed `mlops-routing` namespace centralizes routes and names every backend
namespace explicitly. Do not use this capability to route directly to tenant workloads.

Prefer idempotent modules and handlers. Do not embed shell commands when a maintained Ansible module expresses the operation safely.
Use `kubernetes.core.k8s_info` conditions for Kubernetes reads and readiness,
and `kubernetes.core.k8s` check mode for server-side dry-runs. The bootstrap
`GET /readyz` probe is the only intentional `k3s kubectl` command because it
checks API-server readiness before normal Kubernetes discovery is dependable.
