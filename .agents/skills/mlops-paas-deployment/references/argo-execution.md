# Argo execution

WorkflowTemplates and Argo Events cover:

- Build/package.
- Deploy model worker.
- Delete runtime.
- Evidently drift execution.
- Training submission.
- Training cancellation.

EventBus, EventSource and Sensor run in `argo-events`; Git-managed
WorkflowTemplates and their Workflows run in `mlops-execution`, while PyTorchJobs are
fixed to `user-jobs`. The EventSource accepts only bearer-authenticated requests
from the Control Plane worker, native NATS uses token authentication, and
execution NetworkPolicies enforce those peer boundaries.

The Sensor can only create/list Workflows and every trigger must reference a
Git-managed WorkflowTemplate under `templateReferencing: Secure`. Build/drift,
deploy, delete and training use separate minimum-RBAC service accounts. Resource
UUIDs, callback URLs, immutable image digests, bounded resources and idempotency
must be validated before they survive the event hop.

Training uses the fixed `user-jobs` namespace and Kubeflow Training Operator;
never accept a namespace from an event payload. Disable token automount where
possible and keep tenant code isolated.

Cancellation/delete templates must be idempotent (`ignore-not-found` behavior), wait for runtime termination where required, and report through the correct scoped callback. Never allow a tenant container to authoritatively claim terminal success.
