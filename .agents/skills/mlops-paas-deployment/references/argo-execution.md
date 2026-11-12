# Argo execution

Argo task stdout/stderr is collected by namespace-scoped Alloy into seven-day
Loki/S3 history. Trusted deploy waits for model-loaded readiness, then an exit
handler reports terminal status using a deployment-bound expiring capability.
Never pass that capability to the runtime image. See `docs/runtime-logs.md`.

WorkflowTemplates and Argo Events cover:

- Build/package.
- Deploy model worker.
- Delete runtime.
- Evidently drift execution.
- Training submission.
- Training cancellation.

EventBus, EventSource and Sensor run in `argo-events`; Git-managed
WorkflowTemplates and their Workflows run in `mlops-paas-execution`, while PyTorchJobs are
fixed to `mlops-paas-training`. The EventSource accepts only bearer-authenticated requests
from the Control Plane worker, native NATS uses token authentication, and
execution NetworkPolicies enforce those peer boundaries.

The Sensor can only create/list Workflows and every trigger must reference a
Git-managed WorkflowTemplate under `templateReferencing: Secure`. Build/drift,
deploy, delete and training use separate minimum-RBAC service accounts. Resource
UUIDs, callback URLs, immutable image digests, bounded resources and idempotency
must be validated before they survive the event hop.

Training uses the fixed `mlops-paas-training` namespace and Kubeflow Training Operator;
never accept a namespace from an event payload. Disable token automount where
possible and keep tenant code isolated.

Cancellation/delete templates must be idempotent (`ignore-not-found` behavior), wait for runtime termination where required, and report through the correct scoped callback. Never allow a tenant container to authoritatively claim terminal success.

## Independent training workspaces

- Forward input_contract and job-scoped runtime_config_url/capability through dispatch, Sensor and Workflow. project_id may be empty for training; other task identity checks remain strict. Bind labels/metrics to tenant and job, not just node or optional Project.
- CPU/GPU templates use a trusted init container to prepare Input into emptyDir. Main training mounts the same volume at /prepared with readOnly: true; Work/output remain writable. Keep init and main on the same promoted runner image, with non-root execution, dropped capabilities and no privilege escalation. No SDK is installed for model export; use SM_MODEL_DIR.
- Do not place user environment/secret values, backend encryption key, or shared credentials in events or Input. Only scoped capabilities reach the appropriate trusted stages.
- Check validate_training_workspace_contract.py plus rendering/execution validation. CPU/GPU resources, GPU model affinity and namespace/RBAC checks remain in force. Do not deploy production as a side effect of local rendering.
