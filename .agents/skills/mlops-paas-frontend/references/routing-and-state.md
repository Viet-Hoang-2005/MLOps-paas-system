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
- Main pages use `/dashboard/projects/:projectId/{overview,deployment,monitoring,training,evolution}`; forms `/dashboard/deployments/new`, `/dashboard/monitoring/new`, `/dashboard/training/new` own explicit project selectors. API tokens live at `/dashboard/api-tokens`.
- Header preserves the main section when changing project; from forms/details/account pages it navigates to the chosen project's Overview without retaining old resource IDs. Project boundary remounts state on ID change and rejects unknown IDs.
- Feature owners are projects/deployments/monitoring/training/evolution/api-tokens; no legacy route compatibility. Overview source/reference are read-only Running snapshots; name/description/access are project-level immediate updates.

## Navigation rules

- Back/step navigation uses the same validation and persistence rules as footer actions.
- Dirty local files/forms use SPA blocking plus a confirmation modal; `beforeunload` covers refresh/close.
- Direct URLs missing required IDs must route to the earliest recoverable step.
- Do not use component-local tab state when the route represents the tab.
