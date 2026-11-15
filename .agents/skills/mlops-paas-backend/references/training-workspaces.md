# Independent training workspaces

## Workspace-owned drafts and immutable runs

- TrainingWorkspace owns editable entries/Secrets and configuration. TrainingJob has a required workspace FK and at most one execution; it has no Editing state or mutable entries.
- POST /api/training-workspaces/ creates a draft without Project/Docker requirements. Workspace PATCH/entries/Secrets require revision and no active run/reservation/cleanup. POST /{workspace}/runs/ takes revision/run_key and creates a new job. Parent row lock and conditional unique constraint prevent concurrent active runs; replay returns the original job.
- Snapshot I/O stays outside transactions with submission tokens and a ten-minute lease. Admission snapshots Environment/Secrets/config, reserves quota/resources, sets submitted_at, and enqueues on_commit. Failed preparation keeps the draft and a Failed job record; recovery fences stale writers and schedules scoped cleanup.
- Draft objects use users/{tenant}/training/workspaces/{workspace}/draft/objects/. Each job has independent Input/Output under users/{tenant}/training/jobs/{job}/. Never read the current workspace as historical Input.
- There are no public job create/PATCH/submit/retry/clone endpoints. Return to the existing workspace to edit and Run again. Existing encrypted Secret snapshots cannot restore revoked Secrets into a draft.
- Workspace deletion cancels/waits for all jobs before storage/DB cleanup. Any Build/Version reference blocks job/workspace deletion; preserve quota ledgers and Project-independent ownership. Job deletion keeps the draft. See docs/dev/training-workspaces.md.

## Runtime and model output

- New jobs use input_contract=workspace. Their unified archive is prepared before tenant code: an asynchronous labeled Docker helper fills a per-job named volume; a Kubernetes init container fills an emptyDir. Main training mounts Input read-only; runner checks the actual mount flag. Work/output are writable and no host paths are mounted.
- SM_CHANNEL_TRAIN is unified Input; MLOPS_WORK_DIR is writable working directory; SM_MODEL_DIR receives the official model; SM_OUTPUT_DIR receives supported metrics/metadata. No mlops SDK or export_model call is required. Root requirements.txt is the single training dependency source. Keep legacy jobs on their original input contract.
- Success requires user-process success, nonempty valid model output, and verified upload. Reject links, special files, unsafe paths and configured size/count excesses before metadata/tracking and packaging; never deserialize untrusted models to validate them. Do not collect all of Work.
- Preserve runtime UUID and tenant labels for helper adoption/recovery and cleanup. Check ownership before removing containers or volumes. Preparation must not block a Celery task waiting for dataset download. Retain cancellation, deadline and worker-restart recovery.

## Storage, assignment and deletion

- New storage is users/{tenant}/training/jobs/{job}/, with input/code/source.zip (unified Input), input/data/data.zip (empty compatibility archive), output/model.tar.gz and mlflow/artifacts/. Draft objects live in users/{tenant}/training/workspaces/{workspace}/draft/objects/. Snapshot archives use input/submissions/{submission_token}/code/source.zip and the corresponding data archive.
- Legacy jobs retain storage_layout=project and immutable storage_project_id. Use training_prefix_for and expected_training_uris; never derive paths from the newly assigned Project. Runtime project identity is the original storage_project_id or empty for native tenant jobs, even after assignment.
- POST /api/training-jobs/{id}/project/ accepts an output_revision and either an owned existing Project or new_project metadata. Require completed job plus verified model, allow replay to the same Project, reject switching to another. Save supplemental artifacts/build dependencies at output_revision; never change the trained model, training snapshot or Model Preview, and never auto-build/register/deploy. Build accepts only assigned successful jobs with available models.
- Project deletion stops active training and waits for confirmation. Copy legacy objects to tenant/job storage, verify checksums, checkpoint and update pointers before deleting the Project prefix. Failed copy/stop blocks deletion and can retry. Preserve jobs, logs, artifacts and quota; job deletion owns all its draft objects and snapshots.

## Secrets

- TRAINING_SECRET_ENCRYPTION_KEY is a dedicated trusted-backend Fernet key; no default, and no key in the runner. Missing key disables Secrets only. API reads return names/metadata, never values.
- Snapshot encrypted values at submit. Deliver decrypted runtime configuration through a job-bound expiring one-use capability, not Input archives, ordinary API reads or event payloads. Install requirements before fetching Secrets. Reject reserved platform environment names.
- New runs use current workspace Secrets and snapshot ciphertext for that job. Deleted Secrets cannot be reissued from history. Mask known values in streaming and captured logs; code receiving a Secret can still disclose it intentionally.

## Verification and rollout

Original migrations are edited for a clean development schema; the operator resets DB/S3. Update Control Plane/workers and runner together. Kubernetes init and main containers use the same promoted image. See docs/dev/training-model-output.md for the current contract and docs/dev/training-workspaces.md for the disposable Docker/S3 end-to-end check. Test ownership, revisions, retry, file rules, RO mounts, verified upload, assignment and resumable preservation before Project cleanup. Rendering manifests is offline; deployment requires its own authorization.

## Workspace downloads

Output contract v2 is the only output contract. SM_MODEL_DIR holds raw models.
Archive retention: index _mlops files privately under output/internal/ alongside
public Model/Metadata indexing. Enqueue cleanup_output_archive only after commit;
it deletes the exact scoped archive with retry/backoff. Verified replay must not
HEAD or reopen that archive. Never expose private rows by UUID, path or download-all.
SM_OUTPUT_DIR holds original reports. The private package has model/, metadata/,
_mlops/. Completion queues the registered output finalizer; only after complete
verification/materialization may the job become Completed. Keep attempt-isolated
object keys, runtime finish timestamps and cancellation fences. Public APIs use
public_outputs(), never the archive or _mlops, including UUID/path/download-all.

Assignment requires explicit model_id and six optional slot UUIDs or JSON uploads
under output_revision. Validate ownership, scope, checksum and JSON role before
atomic assignment. No filename inference, singleton defaults or Preview mutation.
Build snapshots the saved selection; never search/extract an archive for model or
missing metadata. See docs/dev/training-model-output.md. Edit the original
artifact_selection migration; the operator resets development DB/S3.

GET /training-jobs/{job}/input/download/ and /outputs/download/ authorize the owning account before storage access and return attachments, accepting only an optional relative path. A file selection returns the exact bytes; a folder selection returns a ZIP rooted at that folder; no selection returns the entire area as a ZIP. Workspace Input downloads read draft objects with a revision check; job Input downloads always read the frozen ZIP, never mutable entries. Empty selections are unavailable. Keep safe-path/job-prefix/checksum validation and binary-safe streaming. Derived ZIPs use bounded temporary files, not persistent S3 objects; close streams on success/error and after the HTTP response.

Training result notifications include workspace_id and job_id as public UUIDs; link to /dashboard/training/workspaces/{workspace}/job/{job}. Frontend job detail tabs are removed; job APIs remain used by Workspace snapshots and assignment.

Run returns Pending/202 immediately and enqueues Input preparation on commit. Preparation claims a submission token before S3 I/O, has a ten-minute deadline, no automatic retry, and cannot reserve quota until admission. FE opens the job snapshot immediately and shows Preparing Input with loading Editor until submitted_at; failed preparation links back to current Workspace. See docs/dev/training-workspaces.md.
