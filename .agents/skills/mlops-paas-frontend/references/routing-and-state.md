# Routing and state

## Route conventions

- Routes are lazy-loaded in the app router.
- The URL is the durable source for selected project, job, build, run, version, and active detail tab.
- localStorage may be fallback state, not a replacement for route identity.
- Coordinators render nested pages through `Outlet` and provide a typed Outlet context.
- Child pages do not duplicate coordinator queries or lifecycle state.

## Current coordinated workflows

- Project creation/edit is one Preview form; deployment wizard is Build → explicit Register → Deploy. Editing Preview never changes Running snapshots.
- Training creation: Metadata → Source → Execution.
- Training detail: overview, logs, metrics, artifacts, and config nested routes.
- Main pages use `/dashboard/projects/:projectId/{overview,deployment,monitoring,training,evolution}`; forms `/dashboard/deployment/build/new`, `/dashboard/monitoring/new`, `/dashboard/training/new` own explicit project selectors. API tokens live at `/dashboard/api-tokens`.
- Build selects Preview/Training via URL `projectId/source/jobId`, snapshots inputs, and persists `buildId`. Register polls until `registered` plus `version_id`, then opens `/dashboard/deployment/run/:projectId/:buildId` without deploying. Run validates registered Build/project/version, changes Build route when selecting another version, and creates deployment only on explicit Terminal action; `deploymentId` query restores the attempt/logs. Evolution only navigates to Run. No legacy create-deployment route or step query.
- Header preserves the main section when changing project; from forms/details/account pages it navigates to the chosen project's Overview without retaining old resource IDs. Project boundary remounts state on ID change and rejects unknown IDs.
- Feature owners are projects/deployments/monitoring/training/evolution/api-tokens; no legacy route compatibility. Overview source/reference are read-only Running snapshots; name/description/access are project-level immediate updates.

## Navigation rules

- Local Overview metrics poll Docker snapshots at 5s while foregrounded; retain at most 60 points/5 minutes only for the mounted page. Reset for new Running deployment, skip RPS across counter resets/outages, and don't show stale values as current measurements. Production keeps its separate Prometheus history mode.

- Back/step navigation uses the same validation and persistence rules as footer actions.
- Dirty local files/forms use SPA blocking plus a confirmation modal; `beforeunload` covers refresh/close.
- Direct URLs missing required IDs must route to the earliest recoverable step.
- Do not use component-local tab state when the route represents the tab.
