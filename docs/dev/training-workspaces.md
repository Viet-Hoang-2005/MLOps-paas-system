# Training workspaces and runs

A TrainingWorkspace owns editable Input entries, Environment, encrypted Secrets,
entry point and resource defaults. Each Run creates a separate TrainingJob with
an immutable Input archive and execution configuration. Neither entity has a name.

## Routes and UI

- `/dashboard/training/workspaces/{workspaceId}` opens the current draft, even
  after it has produced jobs.
- `/dashboard/training/workspaces/{workspaceId}/jobs/{jobId}` opens that job's
  read-only snapshot, logs, metrics and Output. The server validates membership.
- TrainingJobDialog lists paginated runs. Back to current Workspace only navigates;
  it never creates a workspace or restores an old snapshot.
- Environment/Secrets stay in the Editor toolbar. Historical Secrets expose names
  only. Assignment selects a completed job and its explicit Model/Metadata files.

## API and ownership

`GET/POST /api/training-workspaces/` lists/creates account-owned drafts.
`GET/PATCH/DELETE /api/training-workspaces/{id}/` reads, revision-checks settings,
or requests asynchronous deletion. Entries, Secrets and draft Input downloads
are scoped beneath this workspace endpoint.

`POST /api/training-workspaces/{id}/runs/` takes `revision` and `run_key`.
`GET /api/training-workspaces/{id}/jobs/` returns `training_jobs`, `count`, `page`
and `page_size`; `jobs/{jobId}/` validates both identities. Logs, snapshots,
Output, cancellation, assignment and Build remain job-scoped.

Public Editing-job creation, PATCH, submit, retry and clone are removed. Internal
callers use create_workspace/run_workspace; there is no automatic resubmission.

## Data and storage

- TrainingWorkspace: owner, UUID, revision, entry_point, environment, framework,
  CPU/RAM/GPU/runtime defaults, deletion metadata and timestamps.
- TrainingWorkspaceEntry: workspace FK, UUID, relative_path, kind, s3_uri,
  checksum, size_bytes, content_type and timestamps; includes real empty folders.
- TrainingWorkspaceSecret: workspace FK, name, Fernet ciphertext and timestamps.
- TrainingJob: workspace FK, immutable owner, optional Project, input_revision,
  snapshot URIs, entry point/requirements, execution resource fields,
  environment_snapshot/secret_snapshot, submission/runtime/tracking and results.
- TrainingOutput: one indexed Model/Metadata/private _mlops file per row. Artifact
  selection and output_revision belong to the job, never to the workspace.

Draft objects use `users/{tenant}/training/workspaces/{workspace}/draft/objects/`.
Snapshots and outputs use `users/{tenant}/training/jobs/{job}/`. Renaming draft
files does not rename their immutable S3 objects. See training-model-output.md.

## Admission, recovery and deletion

Only one job per workspace can be active. A workspace row lock and conditional
unique constraint serialize Run. Active reservations or cleanup_pending also
keep the workspace locked after a terminal status. Invalid revision/configuration
creates no job. Preparation creates Pending with a fenced token and ten-minute
lease; admission reserves resources/quota and enqueues on_commit. Preparation
failure creates a Failed history record without altering the draft. An expired
preparation is fenced and its submission prefix scheduled for cleanup. Replay of
the same run_key returns the same job, including a failed preparation.

Job deletion retains the draft. Workspace deletion cancels all runs, waits for
runtime cleanup, then removes job data and finally draft data. Any Build/Version
reference blocks deletion. Failures retain state for retry. Project deletion
keeps workspace/job records and follows existing runtime-stop/preservation rules.
Quota ledgers are retained independently.

## Development rollout

Original migrations were edited; no migration or adapter converts existing data.
The operator must reset development DB/S3 and apply migrations before application
acceptance. This implementation does not perform that reset or deploy a cluster.
Run backend/runner tests, FE tests/lint/build, fresh-schema migration checks and
offline Kubernetes contract validation. PostgreSQL concurrency and live Docker
CPU/GPU acceptance require their respective disposable environments.
