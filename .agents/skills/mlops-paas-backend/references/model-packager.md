# Model packager

The packager receives immutable manual or training Build inputs, creates an MLflow-compatible package, and builds an image through Docker locally or Kaniko in production.

- Identity is `BUILD_ID`; project/image repository fields are separate.
- Resolve supported flavors and safe archive extraction before loading artifacts.
- Parse user requirements and conda pip dependencies without trusting archive paths/symlinks.
- Preserve relative package trees and choose deterministic model files.
- Use presigned GET/PUT URLs rather than AWS credentials in the job.
- Stream logs to the Build runtime-log key and call the Build webhook idempotently.
- Docker and Kaniko produce `image-{project_uuid}:build-{build_uuid}`; successful registration adds `vN` and records immutable identity.
- A failed dependency installation must fail the Build; do not hide it behind a shell `|| echo`.

Build, test-zip, and notify dispatch must remain explicit and independently testable.
