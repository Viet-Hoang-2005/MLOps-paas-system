# Independent training workspaces

## Job-owned editing and submission

- A TrainingJob UUID owns its editable workspace. TrainingJobEntry/TrainingJobSecret reference the job directly; there is no TrainingWorkspace model or public workspace ID.
- POST /api/training-jobs/ creates Editing without a Project or available Docker daemon. PATCH settings and entries requires revision and Editing; persist settings before submit. POST /{id}/submit/ takes revision/run_key and freezes the same UUID, not a new run.
- Pending is snapshot preparation with a fenced submission token and a ten-minute lease. Stage I/O outside transactions; submission-scoped object paths prevent stale writers overwriting newer Input. Admission atomically snapshots config, reserves resources/quota, sets submitted_at and Queued, then enqueues on_commit. Preparation failure returns Editing; accepted jobs never do.
- Editing/Pending before admission have no runtime capability, quota reservation or runtime duration. Watchers only observe admitted jobs. Stale preparation recovery fences writers; draft deletion schedules storage cleanup without runtime cancel.
- Retry (failed/cancelled) and clone (terminal) take creation_key, copy frozen Input to a new Editing UUID, never outputs/logs/reservations. Copy only currently existing encrypted Secrets belonging to the source owner; never resurrect secret_snapshot. Terminal jobs permit Secret revocation without changing the execution snapshot.
- Preserve real empty folders, the single root requirements.txt rules and CSV upload validation. Environment and Secrets stay outside downloadable files. Input is immutable after submit, including after completion.

## Runtime and model output

- New jobs use input_contract=workspace. Their unified archive is prepared before tenant code: an asynchronous labeled Docker helper fills a per-job named volume; a Kubernetes init container fills an emptyDir. Main training mounts Input read-only; runner checks the actual mount flag. Work/output are writable and no host paths are mounted.
- SM_CHANNEL_TRAIN is unified Input; MLOPS_WORK_DIR is writable working directory; SM_MODEL_DIR receives the official model; SM_OUTPUT_DIR receives supported metrics/metadata. No mlops SDK or export_model call is required. Root requirements.txt is the single training dependency source. Keep legacy jobs on their original input contract.
- Success requires user-process success, nonempty valid model output, and verified upload. Reject links, special files, unsafe paths and configured size/count excesses before metadata/tracking and packaging; never deserialize untrusted models to validate them. Do not collect all of Work.
- Preserve runtime UUID and tenant labels for helper adoption/recovery and cleanup. Check ownership before removing containers or volumes. Preparation must not block a Celery task waiting for dataset download. Retain cancellation, deadline and worker-restart recovery.

## Storage, assignment and deletion

- New storage is users/{tenant}/training/jobs/{job}/, with input/code/source.zip (unified Input), input/data/data.zip (empty compatibility archive), output/model.tar.gz and mlflow/artifacts/. Draft objects live in users/{tenant}/training/jobs/{job}/draft/objects/. Snapshot archives use input/submissions/{submission_token}/code/source.zip and the corresponding data archive.
- Legacy jobs retain storage_layout=project and immutable storage_project_id. Use training_prefix_for and expected_training_uris; never derive paths from the newly assigned Project. Runtime project identity is the original storage_project_id or empty for native tenant jobs, even after assignment.
- POST /api/training-jobs/{id}/project/ accepts an output_revision and either an owned existing Project or new_project metadata. Require completed job plus verified model, allow replay to the same Project, reject switching to another. Save supplemental artifacts/build dependencies at output_revision; never change the trained model, training snapshot or Model Preview, and never auto-build/register/deploy. Build accepts only assigned successful jobs with available models.
- Project deletion stops active training and waits for confirmation. Copy legacy objects to tenant/job storage, verify checksums, checkpoint and update pointers before deleting the Project prefix. Failed copy/stop blocks deletion and can retry. Preserve jobs, logs, artifacts and quota; job deletion owns all its draft objects and snapshots.

## Secrets

- TRAINING_SECRET_ENCRYPTION_KEY is a dedicated trusted-backend Fernet key; no default, and no key in the runner. Missing key disables Secrets only. API reads return names/metadata, never values.
- Snapshot encrypted values at submit. Deliver decrypted runtime configuration through a job-bound expiring one-use capability, not Input archives, ordinary API reads or event payloads. Install requirements before fetching Secrets. Reject reserved platform environment names.
- Retry creates an Editing job from immutable input, rechecks current Secret access after storage copy, and never submits automatically; deleted Secrets cannot be reissued from history. Mask known values in streaming and captured logs/bundles. Code given a Secret can still disclose it intentionally.

## Verification and rollout

Apply additive training migrations, then update Control Plane/workers and runner image together. Kubernetes init and main containers use the same promoted image. See docs/dev/training-model-output.md for the current contract and services/control-plane/scripts/verify_training_workspace.py for the disposable Docker/S3 end-to-end check. Test ownership, revisions, retry, file rules, RO mounts, verified upload, assignment and resumable preservation before Project cleanup. Rendering manifests is offline; deployment requires its own authorization.
