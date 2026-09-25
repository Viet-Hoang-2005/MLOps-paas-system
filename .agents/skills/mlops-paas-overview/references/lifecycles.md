# Core lifecycles

## Present, Draft, Evolution, deployment

1. A ModelProject owns one editable ModelDraft. The initial draft requires a model and reference dataset; source code is optional.
2. Save Draft creates an immutable ModelDraftRevision and immutable revision asset objects. Builds always read that saved revision, never mutable working assets.
3. A successful Draft build registers a ModelVersion with its required reference DatasetSnapshot and immutable image artifact. Evolution rebuilds from a ModelVersion's model, reference data, code, and metadata inputs; it does not clone package or image artifacts.
4. Deploy an image-bearing ModelVersion to one target (`staging` or `production`). Runtime image identity comes from the version artifact; Build is optional lineage.
5. Only a healthy deployment updates the alias with the target's name. Present reports production alias separately from current endpoint health.

Project name and description are mutable project metadata. Version artifacts and reference snapshots are immutable.

## Draft uploads

1. The API creates a user/project/draft-scoped upload session and object key; clients complete uploads by upload ID, never by supplying an S3 URI.
2. Completion validates ownership, object key, size, checksum, media type, and archive safety before publishing the working asset.
3. Save uses optimistic revision checking and copies working assets into an immutable revision prefix. Failed copies leave the previous saved snapshot intact.
4. Discard restores the saved snapshot and invalidates stale client revisions. A build success resets Draft to the exact revision used; failure leaves the saved revision available.

## Training

1. Select or create a ModelProject.
2. Require a source ZIP and training dataset for each job; snapshot both in the job's own input prefix, independently of Draft.
3. Run a unique TrainingJob through Docker or Argo/Kubeflow.
4. Store a TrainingOutput bundle; failed/cancelled jobs retain lifecycle logs but create no version.
5. Build & Register requires a model artifact and reference data, then allocates a ModelVersion.
6. Deploy that version later from Evolution or Deployment.

## Inference

1. Client calls `/{tenant}/models/{project}/{version}/predict`.
2. Traefik routes to model-server and rewrites to its version endpoint.
3. model-server verifies access, resolves the active worker, and proxies input.
4. After successful inference it publishes a tenant/project/version-scoped event.
5. Consumer persists minimal inference telemetry and successful production-data samples atomically.

## Drift

1. A monitor binds to the immutable reference snapshot owned by a model version; users cannot replace it from Monitoring.
2. Consumer production-data samples or a manual action trigger a DriftRun.
3. Evidently loads reference and production data, creates HTML/JSON/summary reports, and uploads them to S3.
4. An authenticated callback updates PostgreSQL; the UI requests a presigned report URL.

## Deletion

Project deletion marks the project deleting, stops runtimes, removes all project images and S3 prefixes, then deletes or archives database records according to the implemented lifecycle. Never delete only the currently selected version.
