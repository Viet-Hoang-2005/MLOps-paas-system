# Routing and state

## Route conventions

- Routes are lazy-loaded in the app router.
- The URL is the durable source for selected project, job, build, run, version, and active detail tab.
- localStorage may be fallback state, not a replacement for route identity.
- Coordinators render nested pages through `Outlet` and provide a typed Outlet context.
- Child pages do not duplicate coordinator queries or lifecycle state.

## Current coordinated workflows

- Project creation/edit is one Preview form; deployment wizard is Build → explicit Register → Deploy. Editing Preview never changes Running snapshots.
- Training creation: New Workspace on TrainingModelPage directly creates an account-owned Workspace through a mutation, then opens /dashboard/training/workspaces/:workspaceId. The button is disabled while pending and reports errors without navigation; there is no /training/new route. Run creates a new immutable job and opens /dashboard/training/workspaces/:workspaceId/job/:jobId. TrainingJobDialog lists paginated runs; Back to current Workspace only navigates. The /job/:jobId/project page opens assignment with an explicit run selector; Back/Save return to that snapshot. Project is an optional suggestion until Save.
- Training snapshots use TrainingWorkspacePage; logs, metrics, config and Output are composed there. No standalone detail tabs or old job routes. Next requires completed, verified Output and no pending deletion. TrainingJobProjectPage loads the nested owner-scoped workspace/job endpoint independently.
- Main pages use `/dashboard/projects/:projectId/{overview,deployment,monitoring,training,evolution}`; Build/monitoring forms own explicit project selectors; `/dashboard/training` is global with all/unassigned/Project filters and always allows creation. API tokens live at `/dashboard/api-keys`.
- Build selects Preview/Training via URL `projectId/source/jobId`, snapshots inputs, and persists `buildId`. Register polls until `registered` plus `version_id`, then opens `/dashboard/deployment/run/:projectId/:buildId` without deploying. Run validates registered Build/project/version, changes Build route when selecting another version, and creates deployment only on explicit Terminal action; `deploymentId` query restores the attempt/logs. Evolution only navigates to Run. No legacy create-deployment route or step query.
- Header preserves the main section when changing project; from forms/details/account pages it navigates to the chosen project's Overview without retaining old resource IDs. Project boundary remounts state on ID change and rejects unknown IDs.
- Feature owners are projects/deployments/monitoring/training/evolution/api-keys; no legacy route compatibility. Overview source/reference are read-only Running snapshots; name/description/access are project-level immediate updates.

## Navigation rules

- Local Overview metrics poll Docker snapshots at 5s while foregrounded; retain at most 60 points/5 minutes only for the mounted page. Reset for new Running deployment, skip RPS across counter resets/outages, and don't show stale values as current measurements. Production keeps its separate Prometheus history mode.

- Back/step navigation uses the same validation and persistence rules as footer actions.
- Dirty local files/forms use SPA blocking plus a confirmation modal; `beforeunload` covers refresh/close.
- Direct URLs missing required IDs must route to the earliest recoverable step.
- Do not use component-local tab state when the route represents the tab.

## Training workspace state

- Merge code/data into one Input tree and editor. Double-click and selected-row Edit open the same dialog; give drag/drop equivalent menu/keyboard actions. Output is read-only. Keep fixed singleton root requirements.txt rules in both frontend and backend.
- Run awaits every dirty editor/config save, then submits workspace revision/run_key to create a new job. No public Clone/Retry drafts. An active run/reservation/cleanup locks the workspace; a job route displays its own frozen snapshot/logs/output and is always read-only. Closing does not cancel the runtime. Continue requires completed plus verified available model.
- Keep Environment/Secrets outside the tree/downloads. Secret API reads show names only. Show local GPU UUID capability and current memory availability; retain production T4/A10G and quota validation.
- Assignment preserves existing Project metadata and Model Preview. Supplemental artifacts/build requirements use output_revision conflicts. Build chooses Preview or an assigned successful Training Job explicitly. Local frontend state must not silently overwrite a newer server revision.
- Output v2 exposes fixed Model/ and Metadata/ roots only; private model.tar.gz and _mlops are never client download targets. Assignment always uses shared Select for the model, even a singleton. Six Advanced slots default to unused and accept explicit Metadata JSON or FileDropzone upload (1 MiB). Never infer filename roles. Reload saved choices, clear stale source choices on mode changes and block Save after a 409 until reload. See docs/dev/training-model-output.md.

Workspace Input/Output Download follows selection: file -> original file, folder -> folder ZIP, no selection -> entire area ZIP. Disable it when the selection has no files (empty folders included), while busy or when Output is purged; zero-byte files are still downloadable. Save dirty draft buffers before Input downloads. Use the authenticated blob API and Content-Disposition filename; never convert binary downloads to text or silently download the first Output item. Clicking the selected item again clears selection. Read failures must allow retry without locking further editing.

Workspace table columns: UUID, job_count, aggregate state, Created/Updated at, Open/Run/Delete. Run action navigates to Terminal without submitting. Workspace deletion includes all jobs and blocks on Build/Version references. See docs/dev/training-workspaces.md.

Run returns Pending/202 immediately and enqueues Input preparation on commit. Preparation claims a submission token before S3 I/O, has a ten-minute deadline, no automatic retry, and cannot reserve quota until admission. FE opens the job snapshot immediately and shows Preparing Input with loading Editor until submitted_at; failed preparation links back to current Workspace. See docs/dev/training-workspaces.md.

TerminalViewer normalizes TERMINAL_PROGRESS JSON log records into a mutable current row and commits it when done=true; plain log lines remain append-only. Copy uses normalized display text, malformed events stay inert text. Autoscroll compares displayed content so polling without new content does not pull the reader down.
