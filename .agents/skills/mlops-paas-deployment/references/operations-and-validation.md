# Operations and validation

## Local checks

- Render the owning target with `kubectl kustomize <path>` (or the standalone Kustomize used by CI). Check schemas and CRD-dependent assumptions against the matching contract tests under [k8s/verify/validate](../../../../k8s/verify/validate).
- Compare [CI](../../../../.github/workflows/ci.yml) for tooling and its aggregate `pytest k8s/verify/validate/ -v` command. Follow the target workflow's resource and policy dependencies.
- `kubectl apply --dry-run=client` may still use cluster discovery; use pure rendering when only offline checks are in scope.

## Live checks

- When authorized, compare Git revision and rendered Application with Argo sync/health, then inspect the exact owning workload or workflow. Verify the symptom from the caller and collect logs from the correct namespace and resource.
- Use the matching Ansible verify scope for bootstrap, core platform, training or workloads. A successful core-addon check does not establish workload health.
- Roll back a GitOps change through its owning revision or pinned image. Use domain lifecycle APIs for dynamic model runtimes. A database rollback needs its own migration strategy.
