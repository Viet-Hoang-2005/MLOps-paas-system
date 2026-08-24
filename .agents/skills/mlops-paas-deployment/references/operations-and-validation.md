# Operations and validation

## Order

1. Cluster/CRDs/operators.
2. Namespaces, storage classes, external-secret stores.
3. PostgreSQL, Redis, Redpanda, object/registry dependencies.
4. Control Plane and platform gateways.
5. Argo event/workflow execution.
6. Web, monitoring, and external routing.

## Checks

```bash
kubectl kustomize <path>
kubectl apply --dry-run=client -k <path>
kubectl diff -k <path>
kubectl get applications -n argocd
kubectl get pods,svc -A
```

Use server-side dry-run when cluster access and CRDs are available. Validate WorkflowTemplates separately.

## Rollback boundaries

- GitOps manifest: revert/promote a Git commit.
- Application image: restore the prior immutable digest/tag.
- Dynamic deployment: use Control Plane lifecycle/delete/redeploy.
- Database migration: use an explicitly designed reverse/forward migration; never improvise data rollback.

CI builds/scans images; CD authenticates through AWS OIDC, pushes/signs Harbor images, and opens GitOps promotion changes. Verify live workflow before modifying it.
