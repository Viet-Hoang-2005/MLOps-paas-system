# Production task logs and deployment confirmation

## Ownership and access

Terraform creates the private `mlops-paas-runtime-logs` bucket and a
bucket-scoped policy for static workers. It does not grant this policy to
Karpenter training nodes or GitHub Actions. Argo CD installs Loki and Alloy in
`mlops-logging`. Loki retains logs for seven days; an S3 safety-net lifecycle
expires leftover objects after ten days. Empty the logs bucket before Terraform
destroy: it deliberately does not use `force_destroy`.

Alloy has namespace-scoped read-only Pod/log RBAC in `mlops-execution`,
`mlops-model-runtimes`, `user-jobs`, and `mlops-control-plane`. From the Control
Plane it forwards only JSON records written by `emit_tenant_log` (`audience=tenant`
with a valid `task_kind`); platform, framework and inherited-context logs stay in
`kubectl logs`. `task_id`, `task_kind` and `audience` are never inherited from log
context, so a whole Celery task cannot become tenant-visible. No Secret reads, node mounts, privileged
DaemonSet, Control Plane Kubernetes credentials, or public Loki endpoint are
required. Authoritative Pod labels correlate tasks. UUID/Pod become structured
metadata instead of high-cardinality index labels. Logs remain untrusted
presentation data, never lifecycle truth.

Existing task-log APIs authorize resources with tenant-scoped selectors before
generating bounded Loki queries. Clients cannot supply LogQL or namespaces.
Signed cursors bind the task UUID/kind; returned lines are sanitized. Local
Docker retains Redis logs. `uses_loki(backend)` is the single Control Plane switch
for writers and readers; Argo workloads skip Redis when the execution ConfigMap sets
`LOG_STORAGE_BACKEND=loki`, which the validator keeps aligned with `LOKI_URL`. Web polls every two seconds, drains terminal output,
and limits its buffer to 10,000 lines. Loki outages preserve the cursor and do
not change task status.

Loki NetworkPolicy permits only logging, Control Plane and monitoring namespaces.
Grafana has an internal Loki datasource for operators, not tenant log access.
Existing static-worker node IAM credentials remain in use; workload-specific
AWS identity and broader metadata isolation require separate hardening.

## Deployment state

Argo applies Deployment/Service then waits for rollout. Startup/readiness probes
require `/health` to return `model_loaded=true` (ML GET, DL POST). A trusted exit
handler reports terminal status with an expiring deployment-bound HMAC capability.
The capability is never passed to the tenant runtime image.

The Control Plane locks the deployment, handles replay idempotently, updates
Endpoint/cache/event outbox, and exposes authoritative status to Web. Stopped or
deleting resources cannot be revived. Argo no longer polls readiness from Celery.
A one-shot 33-minute deadline marks missing callbacks `unconfirmed`, not success
or necessarily failure. Workflow deadline is 30 minutes; token lifetime is one
hour. Docker deployment polling is unchanged.

Argo Workflows dashboard/API must be operator-only behind authenticated access
(Cloudflare Access/SSO or equivalent). The current chart uses `authModes: server`,
which is not end-user authentication. Workflow arguments contain short-lived
reporter capabilities and existing execution inputs; do not expose them to
tenants or anonymous Internet clients. Validate that external access boundary
before production rollout; this feature does not configure Cloudflare Access.

## Rollout and troubleshooting

Provision S3/IAM before Loki. Deploy the Control Plane image/migration before the
new deploy template, then Web and execution images. Restore any temporary GitOps
pause after validation. Training remains disabled for tenants.

Detailed history starts when Alloy collection and task labels are deployed.
It cannot reconstruct stdout from previously deleted Pods.

For the current live cluster, merging manifests and promoting images are not
atomic. Pause execution Application reconciliation while the new Control Plane
image is built/promoted; resume execution only after API and worker are Ready
on that image and the database migration completed. Otherwise the new template
can call an endpoint that the old image does not implement. Existing Workflows
retain their template snapshot and old completion path; do not resubmit them
with missing new parameters.

Local checks: `python -m k8s.validate.run_all`, validator unit tests, Control Plane
pytest/Ruff/Django checks, and `pnpm lint && pnpm build`. Full Control Plane mypy
currently has pre-existing typing errors; resolve that gate before merging rather
than disabling it. Schema/render checks are not a substitute for runtime smoke.

- Check Loki/Alloy Application health, collector errors and Loki `/ready`.
- Confirm Alloy can read task and Control Plane Pods/logs but not Secrets.
- Compare Pod task labels with UUIDs and inspect structured metadata when output
  is missing. Retry log API errors without discarding the cursor.
- For `unconfirmed`, inspect the Workflow exit handler and callback HTTP result
  before resubmitting. Never derive success from log text.

Rollback the images and template together; do not delete model runtimes,
PostgreSQL state or log data to roll back this feature.
