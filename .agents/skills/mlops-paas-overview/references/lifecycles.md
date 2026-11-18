# Core lifecycles

## Training

1. The Training workspace route edits a persistent draft. Run submits its revision and returns a Pending job after queuing preparation on commit.
2. Celery prepares job-scoped Input and admits resources before dispatch. The job snapshot is immutable; Project assignment is independent.
3. Docker helper or Kubernetes init materializes Input for read-only runtime access. Tenant code writes the model and metadata into their designated output directories.
4. Trusted observation and output verification publish indexed Model/Metadata. The transport archive is cleaned after verification, and private internal rows stay private.
5. Assignment explicitly selects artifacts for a subsequent Build.

Start with [workspace and job contracts](../../mlops-paas-backend/references/training-workspaces.md), then [Trainer v2](../../../../docs/dev/trainer-v2.md) if the issue reaches Kubernetes.

## Build and deploy

1. Django `apps/deployment` snapshots the selected Preview or assigned Training source into a Build. Model Packager prepares the model and build context.
2. Docker builds locally. The production Workflow runs Kaniko, passes `image.tar` to a separate registry push step, and reports completion.
3. Register creates a model version. Deploy creates a separate rollout for that version. The inference gateway routes to the selected serving worker.

For an issue in the production execution chain, follow [Argo execution](../../mlops-paas-deployment/references/argo-execution.md).

## Predict, drift and retrain

1. Model Server validates the principal, resolves the version's worker and returns the inference response.
2. Prediction telemetry is produced asynchronously to Redpanda. Consumer persists records and queues automatic-drift signals via PostgreSQL outbox.
3. Control Plane admits drift work, Evidently compares the selected reference and current production data, and Control Plane records the result and evaluates configured continuous training policy.

Start with [Model Server](../../mlops-paas-backend/references/model-server.md), [Consumer](../../mlops-paas-backend/references/consumer.md) or [Evidently](../../mlops-paas-backend/references/evidently.md) according to the first failing stage.
