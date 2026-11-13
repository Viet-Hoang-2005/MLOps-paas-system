# Routing and state

## Route conventions

- Routes are lazy-loaded in the app router.
- The URL is the durable source for selected project, job, build, run, version, and active detail tab.
- localStorage may be fallback state, not a replacement for route identity.
- Coordinators render nested pages through `Outlet` and provide a typed Outlet context.
- Child pages do not duplicate coordinator queries or lifecycle state.

## Current coordinated workflows

- Project creation/edit is one Preview form; deployment wizard is Build → explicit Register → Deploy. Editing Preview never changes Running snapshots.
- Training creation: Run training → Assign Project. /dashboard/training/new creates an account-owned Editing Training Job and opens /dashboard/training/:jobId/workspace. The same job UUID remains selected through submission/completion; no workspace history selector or separate workspace ID. step=project opens assignment. Project is only an optional suggestion until Save.
- Training detail: overview, logs, metrics, artifacts, config, and project nested routes. Completed unassigned jobs can open project assignment from detail even when their workspace was deleted.
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
- Run awaits every dirty editor/config save, then submits revision/run_key on the same job. Retry/clone navigate to a new Editing UUID. Failure stops submission. An active run locks editing; a submitted job displays its frozen snapshot/logs/output. Closing does not cancel the runtime. Continue requires completed plus verified available model.
- Keep Environment/Secrets outside the tree/downloads. Secret API reads show names only. Show local GPU UUID capability and current memory availability; retain production T4/A10G and quota validation.
- Assignment preserves existing Project metadata and Model Preview. Supplemental artifacts/build requirements use output_revision conflicts. Build chooses Preview or an assigned successful Training Job explicitly. Local frontend state must not silently overwrite a newer server revision.
- Output v2 exposes fixed Model/ and Metadata/ roots only; private model.tar.gz and _mlops are never client download targets. Assignment always uses shared Select for the model, even a singleton. Six Advanced slots default to unused and accept explicit Metadata JSON or FileDropzone upload (1 MiB). Never infer filename roles. Reload saved choices, clear stale source choices on mode changes and block Save after a 409 until reload. See docs/dev/training-model-output.md.

Workspace Input/Output Download follows selection: file -> original file, folder -> folder ZIP, no selection -> entire area ZIP. Disable it when the selection has no files (empty folders included), while busy or when Output is purged; zero-byte files are still downloadable. Save dirty draft buffers before Input downloads. Use the authenticated blob API and Content-Disposition filename; never convert binary downloads to text or silently download the first Output item. Clicking the selected item again clears selection. Read failures must allow retry without locking further editing.
