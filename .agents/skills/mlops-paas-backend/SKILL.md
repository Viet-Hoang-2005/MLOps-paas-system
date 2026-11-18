---
name: mlops-paas-backend
description: Implement or diagnose Python service behavior in MLOps PaaS, including Django APIs, jobs, inference, packaging, training, drift, and backend tests.
---

# MLOps PaaS Backend

Start with the API route, task, or service entry point that reproduces the behavior. Trace through serializers, selectors/services and backend adapters to the state or external side effect they own. Check callers that replay the operation or process late results. In Django, keep state transitions in the owning domain service and dispatch dependent tasks after commit.

- [Control Plane](references/control-plane.md) maps Django apps, auth, request handling and state ownership.
- [Service contracts](references/service-contracts.md) covers internal callbacks, storage, log transport and async recovery.
- [Training workspaces](references/training-workspaces.md) covers Run admission, job snapshots, Output and assignment. Read the [runner reference](references/training-runner.md) when changing the runtime boundary.
- For a worker change, read the relevant service reference: [Consumer](references/consumer.md), [Model Server](references/model-server.md), [ML serving](references/machine-learning-serving.md), [DL serving](references/deep-learning-serving.md), [Model Packager](references/model-packager.md) or [Evidently](references/evidently.md).

Use [backend testing](references/testing.md) to choose the affected tests, Django migration checks and Docker dependency checks. If the change crosses tenancy, callbacks, credentials, or untrusted execution, follow the [security skill](../mlops-paas-security/SKILL.md) for that boundary.
