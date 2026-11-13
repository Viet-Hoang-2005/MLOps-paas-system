# GitOps & Kustomize

## Root Application & Sync Waves

Argo CD manages the cluster using the Application-of-Applications pattern anchored at `k8s/gitops/production/applications.yaml`. Resources are synchronized according to strict **Sync Waves**:

| Plane | Sync Wave | Applications / Resources |
|---|---|---|
| **Cluster Plane** | `-50` | `mlops-prod-cluster-namespaces`, CRDs, PriorityClasses |
| **Addons Plane** | `-40` to `-31` | Traefik, CloudNativePG, Redis Operator, Redpanda Operator, ESO, Loki, Alloy, Prometheus Stack, Harbor |
| **Platform Plane** | `-30` to `-21` | `ClusterSecretStore` (AWS Secrets Manager), Cert-Manager, Kyverno policies |
| **Execution Plane** | `-20` to `-11` | Argo Workflows, Argo Events EventSource/Sensors, Kubeflow Training Operator, Karpenter, KEDA |
| **Workloads Plane** | `0` to `20` | DB Migrations (Wave 0), Control Plane & Celery (Wave 10), Model Server & Consumer (Wave 10), MLflow (Wave 10), Web Dashboard (Wave 20) |

## Operational Caveats & Drift Protections

1. **`redis-operator` Feature Gates Drift:**
   - The upstream chart attempts to pass `FEATURE_GATES` environment variables that cause reconcile loops.
   - Suppressed by setting `featureGates: null` in `k8s/gitops/production/applications/addons/redis-operator.yaml`.
2. **`ExternalSecret` Webhook Defaults Drift:**
   - The ESO mutating webhook injects 4 default fields:
     - `conversionStrategy: Default`
     - `decodingStrategy: None`
     - `metadataPolicy: None`
     - `nullBytePolicy: Ignore`
   - All `ExternalSecret` manifests across `control-plane`, `model-server`, and `redis` explicitly declare these 4 fields to eliminate perpetual Argo CD OutOfSync status.
3. **Loki StatefulSet Field Normalization:**
   - `loki.yaml` configures `ignoreDifferences` for Kubernetes defaulted StatefulSet fields (`revisionHistoryLimit`, `updateStrategy.rollingUpdate.partition`) to prevent perpetual drift.
4. **Alloy Destination Allowlist:**
   - In `addons.yaml`, the `alloy` Application explicitly allows destination namespace `mlops-control-plane` so Alloy can discover and scrape application pods.
5. **Kyverno Image Verification:**
   - Enforces keyless Cosign verification on `registry.mlops-nids-nt114.id.vn/mlops-paas/*` images produced by the repository's `cd.yml` workflow on `main`.
   - Tenant user model images (`user-images/*`) remain exempted until tenant build workflows implement signing.
6. **Namespace Isolation:**
   - No production application or data store reconciles into `default`. Dedicated namespaces: `mlops-system`, `mlops-control-plane`, `mlops-model-runtimes`, `mlops-data`, `mlops-monitoring`, `mlops-execution`.
