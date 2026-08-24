# Production Kubernetes GitOps

`mlops-paas-system` is the single Argo CD root Application. The root owns
AppProjects, public repository descriptors and explicit child Applications;
each child owns one independently observable service or domain.

## Topology

| Plane | Source | Argo CD project |
| --- | --- | --- |
| GitOps control | `k8s/gitops/production` | `default` |
| Cluster configuration | `k8s/cluster` | `mlops-cluster` |
| Cluster add-ons | Pinned Git/Helm sources | `mlops-addons` |
| Shared platform services | `k8s/platform` | `mlops-platform` |
| Argo execution | `k8s/argo` | `mlops-execution` |
| Static workloads | `k8s/apps/overlays/production` | `mlops-workloads` |

`mlops-prod-cluster-karpenter-capacity` owns the production CPU/GPU EC2NodeClasses and
NodePools. Their non-secret cluster identifiers and stable private K3s API DNS
are declared in Git; the K3s join-token value remains in Secrets Manager.
Dynamic model Deployments and PyTorchJobs remain lifecycle-owned resources and
are not adopted by Argo CD.

## Namespace ownership

No GitOps workload or runtime is reconciled into Kubernetes `default`.
Production uses dedicated namespaces: `mlops-control-plane`, `mlops-consumer`,
`mlops-model-server`, `mlops-web`, `mlops-postgres`, `mlops-redis`,
`mlops-redpanda`, `mlops-execution`, `mlops-model-runtimes`, `mlops-routing`
and `mlops-cluster-config`. Cross-owner service calls use fully qualified
cluster DNS names. `user-jobs` remains the fixed namespace for tenant training.

## Cluster configuration

`mlops-prod-cluster-namespaces` owns production Namespace resources from
`k8s/cluster/namespaces` at wave `-50`. Upstream add-on namespace manifests are
removed from their rendered sources so namespace ownership remains single and
explicit.

`mlops-prod-cluster-storage` owns only `ebs-gp3`; the cluster secret-store and
Karpenter capacity each have their own cluster Application. Cluster configuration
consumes installed capabilities but never installs their controllers.

## Secrets

`mlops-prod-cluster-secret-store` owns only the cluster-scoped `ClusterSecretStore`.
Each workload, infrastructure domain, and execution plane owns its own
production `ExternalSecret` beside the manifest that consumes its target
Secret. AWS remains the shared source of values, but no Pod receives a broad
shared application Secret. Secret values must never be committed or printed
during debugging.

## Data and platform services

PostgreSQL, Redis, Redpanda, Harbor and MLflow each have an independent
Application. Runtime-default ignore rules are scoped to the Application that
owns the affected resource.

## Execution

`mlops-prod-execution-argo` owns the EventBus, EventSource, Sensor and their stable
webhook Service in `argo-events`; WorkflowTemplates and Workflow Pods run in
`mlops-execution`, dynamic model Deployments/Services run in `mlops-model-runtimes`,
and training runtime resources remain in `user-jobs`. The six webhook routes use a
dedicated bearer token synchronized into the Control Plane API/worker target
Secrets and the EventSource target Secret. Native NATS uses token authentication,
and reconciled NetworkPolicies permit only the
Control Plane worker to reach the EventSource and only Argo Events components
to reach the EventBus.

The Sensor can only create/list Git-managed-template Workflows. Build/drift,
deploy, delete and training use separate least-privilege Workflow service
accounts; Control Plane API/worker Pods do not mount Kubernetes API tokens.
Resources created by a Workflow remain runtime-owned.

## Workloads

Control Plane, consumer, model-server and web share environment-neutral manifests
under `k8s/apps/base`. Each service has an independent production overlay
under `k8s/apps/overlays/production`; these overlays are the only workload
paths reconciled by Argo CD. GitHub Actions changes only the affected production
overlay and keeps promotion on Git SHA tags during the current phase.

The base image references contain only logical image names and are not deployable
targets. Add future `dev` or `staging` overlays beside `production` rather than
putting environment-specific registry names, tags, ConfigMaps or patches in base.

## Cloudflare and routing

`mlops-prod-platform-cloudflare` owns the Cloudflare Tunnel and its scoped
credential. `mlops-prod-platform-routing` owns Traefik routes and the Traefik
health endpoint in `mlops-routing`. Routes declare backend namespaces explicitly;
the Ansible-owned Traefik configuration enables this controlled cross-namespace
reference. Public exposure changes require a security review.

## Cluster add-ons

Argo CD owns upstream add-ons: AWS EBS CSI, External Secrets, CloudNativePG,
KEDA, Argo Workflows, Argo Events, kube-prometheus-stack, Kyverno, Kubeflow
Training, Karpenter CRDs/controller, Node Feature Discovery and NVIDIA GPU
Operator. `mlops-addons` installs these capabilities; their configuration lives
under `cluster` or `platform`. Ansible owns only K3s, token publication and the Argo CD bootstrap;
there are no ignored or runtime-patched Karpenter controller fields.

## Image verification

`mlops-prod-addon-kyverno` and `mlops-prod-cluster-image-verification` verify only images under
`registry.mlops-nids-nt114.id.vn/mlops-paas/*`. The policy requires a keyless
Cosign signature issued to this repository's `cd.yml` workflow on `main`, then
resolves tags to immutable digests before admission. Unsigned or incorrectly
signed platform images are denied. Third-party images and tenant `user-images/*`
are intentionally outside this policy until their build path gains an isolated
signing identity.

For a clean bootstrap, first dispatch CD with `component=all` from `main` and
merge its GitOps promotion PR. This ensures every platform tag referenced by
the production overlays and WorkflowTemplates has a signature matching the
enforced GitHub Actions identity before Argo CD creates the workloads.

## Deferred security resources

`k8s/security` is intentionally outside every reconciled
Kustomization. Its broad NetworkPolicies and PDBs are not active controls. This
does not include the execution-plane NetworkPolicies in `k8s/argo`, which are
active production resources owned by `mlops-prod-execution-argo`.

## Validation and debugging

```bash
kubectl kustomize --enable-helm k8s
python3 -m k8s.validate.run_all
kubectl get applications -n argocd -L mlops-paas.io/plane,mlops-paas.io/component
kubectl get application -n argocd <application> -o yaml
```

Debug the smallest unhealthy child first. Check its comparison conditions,
rendered source, events and owned resource health before inspecting the root.
Rollback a manifest through Git; do not delete CRDs, stateful resources or
runtime-created workloads to repair an Application status.

Orphan warnings stay enabled. AppProjects ignore only accepted runtime resources
created by CloudNativePG, Kubernetes and Argo Workflows. Monitoring resources
are owned directly by `mlops-prod-addon-monitoring`; a new orphan outside the accepted
identities remains visible as an `OrphanedResourceWarning`.
