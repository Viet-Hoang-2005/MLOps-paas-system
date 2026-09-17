# Core lifecycles

## Manual upload

1. Save latest-only project metadata and workspace source/reference assets.
2. Submit flavor, artifact/package, and optional requirements as a Build snapshot.
3. Build `image-{project_uuid}` with temporary tag `build-{build_uuid}`.
4. On success, allocate the next version and persist image URI/digest and version artifacts.
5. Deploy the selected ready Build/version and expose it through model-server.

## Training

1. Select or create a ModelProject.
2. Snapshot source, reference data, entry point, requirements, flavor, and compute configuration.
3. Run a unique TrainingJob through Docker or Argo/Kubeflow.
4. Store a TrainingOutput bundle; failed/cancelled jobs retain lifecycle logs but create no version.
5. Build & Register packages one successful output into an image and allocates one version.
6. Deploy that version later from Model Evolution.

## Inference

1. Client calls `/{tenant}/models/{project}/{version}/predict`.
2. Traefik routes to model-server and rewrites to its version endpoint.
3. model-server verifies access, resolves the active worker, and proxies input.
4. After successful inference it publishes a tenant/project/version-scoped event.
5. Consumer persists minimal inference telemetry and successful production-data samples atomically.

## Drift

1. A monitor binds a reference dataset and threshold to a model version.
2. Consumer production-data samples or a manual action trigger a DriftRun.
3. Evidently loads reference and production data, creates HTML/JSON/summary reports, and uploads them to S3.
4. An authenticated callback updates PostgreSQL; the UI requests a presigned report URL.

## Deletion

Project deletion marks the project deleting, stops runtimes, removes all project images and S3 prefixes, then deletes or archives database records according to the implemented lifecycle. Never delete only the currently selected version.
